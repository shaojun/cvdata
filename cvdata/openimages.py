import argparse
import concurrent.futures
import io
import logging
import os
from typing import Dict, List, Set
import warnings

import boto3
import botocore
import lxml.etree as etree
import pandas as pd
import PIL.Image as Image
import requests
from tqdm import tqdm

# OpenImages URL locations
_OID_v4 = "https://storage.googleapis.com/openimages/2018_04/"
_OID_v5 = "https://storage.googleapis.com/openimages/v5/"

# ignore the connection pool is full warning messages from boto
warnings.filterwarnings("ignore")

# ------------------------------------------------------------------------------
# set up a basic, global _logger which will write to the console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d  %H:%M:%S",
)
_logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------
def class_label_codes(
        class_labels: List[str],
) -> Dict:

    # get the class descriptions CSV from OpenImages and read into a DataFrame
    classes_csv = "class-descriptions-boxable.csv"
    url = _OID_v5 + classes_csv
    r = requests.get(url, allow_redirects=True)
    df_classes = pd.read_csv(io.BytesIO(r.content), header=None)

    labels_to_codes = {}
    for class_label in class_labels:
        labels_to_codes[class_label.lower()] = \
            df_classes.loc[df_classes[1] == class_label].values[0][0]

    # return the label's OpenImages code
    return labels_to_codes


# ------------------------------------------------------------------------------
def download_dataset(
        dest_dir: str,
        class_labels: List[str],
        annotation_format: str,
        exclusions_path: str,
) -> Dict:
    """
    Downloads the
    :param dest_dir:
    :param class_labels:
    :param annotation_format:
    :param exclusions_path:
    :return: images directory and annotations directory
    """

    # get the OpenImages image class codes for the specified class labels
    label_codes = class_label_codes(class_labels)

    # build the directories for each class label
    image_class_directories = {}
    for class_label in label_codes.keys():

        # create directories to hold the images and annotations for the image class
        images_dir = os.path.join(dest_dir, class_label, "images")
        os.makedirs(images_dir, exist_ok=True)
        annotations_dir = os.path.join(dest_dir, class_label, annotation_format)
        os.makedirs(annotations_dir, exist_ok=True)
        image_class_directories[class_label] = {
            "images_dir" : images_dir,
            "annotations_dir": annotations_dir,
        }

    # get the IDs of questionable files marked for exclusion
    if exclusions_path is not None:

        # read the file IDs from the exclusions file
        with open(exclusions_path, "r") as exclusions_file:
            exclusion_ids = set([line.rstrip('\n') for line in exclusions_file])

    else:
        exclusion_ids = None

    # OpenImages is already split into sections so we'll need to loop over each
    for split_section in ("train", "validation", "test"):

        # get a dictionary of class labels to GroupByDataFrames
        # containing bounding box info grouped by image IDs
        label_bbox_groups = bounding_boxes(split_section, label_codes, exclusion_ids)

        for class_label in label_codes.keys():

            # get the bounding boxes grouped by image and the collection of image IDs
            bbox_groups = label_bbox_groups[class_label]
            image_ids = bbox_groups.groups.keys()

            # download the images
            _logger.info(f"Downloading {split_section} images for class \'{class_label}\'")
            download_images(
                image_ids,
                split_section,
                image_class_directories[class_label]["images_dir"],
            )

            # build the annotations
            _logger.info(
                f"Creating {split_section} annotations ({annotation_format}) "
                f"for class \'{class_label}\'"
            )
            build_annotations(
                annotation_format,
                image_ids,
                bbox_groups,
                class_label,
                image_class_directories[class_label]["images_dir"],
                image_class_directories[class_label]["annotations_dir"],
            )

    return image_class_directories


# ------------------------------------------------------------------------------
def download_images(
        image_ids: List[str],
        section: str,
        images_directory: str,
):

    # we'll download the images from AWS S3 so we'll need a boto S3 client
    s3_client = boto3.client(
        's3',
        config=botocore.config.Config(signature_version=botocore.UNSIGNED),
    )

    # use a ThreadPoolExecutor to download the images in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:

        # create an iterable list of function arguments
        # that we'll map to the download function
        download_args_list = []
        for image_id in image_ids:
            image_file_name = image_id + ".jpg"
            download_args = {
                "s3_client": s3_client,
                "image_file_object_path": section + "/" + image_file_name,
                "dest_file_path": os.path.join(images_directory, image_file_name),
            }
            download_args_list.append(download_args)

        # use the executor to map the download function to the iterable of arguments
        list(tqdm(executor.map(download_image, download_args_list),
                  total=len(download_args_list)))


# ------------------------------------------------------------------------------
def build_annotations(
        annotation_format: str,
        image_ids: List[str],
        bbox_groups: pd.core.groupby.DataFrameGroupBy,
        class_label: str,
        images_directory: str,
        annotations_directory: str,
):

    # use a ProcessPoolExecutor to download the images in parallel
    with concurrent.futures.ProcessPoolExecutor() as executor:

        # create an iterable list of function arguments
        # that we'll map to the annotation builder function
        build_args_list = []
        for image_id in image_ids:

            # get all bounding boxes in the image for the label
            bboxes = bbox_groups.get_group(image_id)[['XMin', 'XMax', 'YMin', 'YMax']].values.tolist()

            # build a dictionary of arguments for the build_annotation function
            # that will be called by one of the process pool's worker processes
            build_args = {
                "annotation_format": annotation_format,
                "bboxes": bboxes,
                "class_label": class_label,
                "image_id": image_id,
                "images_dir": images_directory,
                "annotations_dir": annotations_directory,
            }
            build_args_list.append(build_args)

        # use the executor to map the build function to the iterable of arguments
        list(tqdm(executor.map(build_annotation, build_args_list),
                  total=len(build_args_list)))


# ------------------------------------------------------------------------------
def build_annotation(arguments: Dict):

    if arguments["annotation_format"] == "pascal":

        # write a PASCAL VOC file for this image
        # using all bounding boxes in the image's group
        to_pascal(
            arguments["bboxes"],
            arguments["class_label"],
            arguments["image_id"],
            arguments["images_dir"],
            arguments["annotations_dir"],
        )

    elif arguments["annotation_format"] == "darknet":
        # TODO
        pass
    else:
        # TODO
        # logger.warn("Unsupported format")
        pass


# ------------------------------------------------------------------------------
def bounding_boxes(
        section: str,
        label_codes: Dict,
        exclusion_ids: Set[str],
) -> Dict:
    """
    Gets a pandas DataFrameGroupBy object containing bounding boxes for an image
    class grouped by image ID.

    :param section: the relevant split section, "train", "validation", or "test"
    :param label_codes: dictionary with class labels mapped to the
        corresponding OpenImages-specific code of the image class
    :param exclusion_ids: file IDs that should be excluded
    :return: DataFrameGroupBy object with bounding box columns grouped by image IDs
    """

    # get the annotations CSV for the section
    bbox_csv_name = section + "-annotations-bbox.csv"
    url = _OID_v4 + section + "/" + bbox_csv_name
    response = requests.get(url, allow_redirects=True)
    if response.status_code != 200:
        raise ValueError(
            f"Failed to get bounding box information for split section {section} "
            f"-- Invalid response (status code: {response.status_code}) from {url}",
        )
    df_images = pd.read_csv(io.BytesIO(response.content))

    # remove any rows which are identified to be excluded
    if exclusion_ids and (len(exclusion_ids) > 0):
        df_images = df_images[~df_images["ImageID"].isin(exclusion_ids)]

    # filter out images that are occluded, truncated, group, depiction, inside, etc.
    for reject_field in ("IsOccluded", "IsTruncated", "IsGroupOf", "IsDepiction", "IsInside"):
        df_images = df_images[df_images[reject_field] == 0]

    # drop the columns we won't need, keeping only
    # the image ID, label name and bounding box columns
    unnecessary_columns = [
        "IsOccluded",
        "IsTruncated",
        "IsGroupOf",
        "IsDepiction",
        "IsInside",
        "Source",
        "Confidence",
    ]
    df_images.drop(unnecessary_columns, axis=1, inplace=True)

    # create a dictionary and populate it with class labels mapped to
    # GroupByDataFrame objects with bounding boxes grouped by image ID
    labels_to_bounding_box_groups = {}
    for class_label, class_code in label_codes.items():

        # filter the DataFrame down to just the images for the class label
        df_label_images = df_images[df_images["LabelName"] == class_code]

        # drop the label name column since it's no longer needed
        df_label_images.drop(["LabelName"], axis=1, inplace=True)

        # map the class label to a GroupBy object with each
        # group's row containing the bounding box columns
        labels_to_bounding_box_groups[class_label] = \
            df_label_images.groupby(df_images["ImageID"])

    # return the dictionary we've created
    return labels_to_bounding_box_groups


# ------------------------------------------------------------------------------
def to_pascal(
        bboxes: List[List[float]],
        label: str,
        image_id: str,
        images_dir: str,
        pascal_dir: str,
) -> str:
    """
    Writes a PASCAL VOC (XML) annotation file containing the bounding boxes for
    an image.

    :param bboxes: iterable of lists of bounding box coordinates [xmin, ymin, xmax, ymax]
    :param label: class label
    :param image_id: ID of the image file (typically the image file name
        minus ".jpg" or ".png")
    :param images_dir: directory where the image file is located
    :param pascal_dir: directory where the PASCAL file should be written
    :return: path to the PASCAL VOC file
    """

    # get the image dimensions
    image_path = os.path.join(images_dir, image_id + ".jpg")
    image = Image.open(image_path)
    img_width, img_height = image.size
    img_depth = image.layers

    normalized_image_path = os.path.normpath(image_path)
    folder_name, image_file_name = normalized_image_path.split(os.path.sep)[-2:]

    annotation = etree.Element('annotation')
    folder = etree.SubElement(annotation, "folder")
    folder.text = folder_name
    filename = etree.SubElement(annotation, "filename")
    filename.text = image_file_name
    path = etree.SubElement(annotation, "path")
    path.text = normalized_image_path
    source = etree.SubElement(annotation, "source")
    database = etree.SubElement(source, "database")
    database.text = "OpenImages"
    size = etree.SubElement(annotation, "size")
    width = etree.SubElement(size, "width")
    width.text = str(img_width)
    height = etree.SubElement(size, "height")
    height.text = str(img_height)
    depth = etree.SubElement(size, "depth")
    depth.text = str(img_depth)
    segmented = etree.SubElement(annotation, "segmented")
    segmented.text = "0"
    for bbox in bboxes:
        obj = etree.SubElement(annotation, "object")
        name = etree.SubElement(obj, "name")
        name.text = label
        pose = etree.SubElement(obj, "pose")
        pose.text = "Unspecified"
        truncated = etree.SubElement(obj, "truncated")
        truncated.text = "0"
        difficult = etree.SubElement(obj, "difficult")
        difficult.text = "0"
        bndbox = etree.SubElement(obj, "bndbox")
        xmin = etree.SubElement(bndbox, "xmin")
        xmin.text = str(max(0, int(bbox[0] * img_width)))
        xmax = etree.SubElement(bndbox, "xmax")
        xmax.text = str(min(img_width - 1, int(bbox[1] * img_width)))
        ymin = etree.SubElement(bndbox, "ymin")
        ymin.text = str(max(0, int(bbox[2] * img_height)))
        ymax = etree.SubElement(bndbox, "ymax")
        ymax.text = str(min(img_height - 1, int(bbox[3] * img_height)))

    # write the XML to file
    pascal_file_path = os.path.join(pascal_dir, image_id + ".xml")
    with open(pascal_file_path, 'w') as pascal_file:
        pascal_file.write(etree.tostring(annotation, pretty_print=True, encoding='utf-8').decode("utf-8"))

    return pascal_file_path


# ------------------------------------------------------------------------------
def download_image(arguments: Dict):

    with open(arguments["dest_file_path"], "wb") as dest_file:
        arguments["s3_client"].download_fileobj(
            "open-images-dataset",
            arguments["image_file_object_path"],
            dest_file,
        )


# ------------------------------------------------------------------------------
if __name__ == "__main__":
    """
    Usage:
    $ python openimages_fetch.py --base_dir /data/datasets/openimages \
          --format pascal_dir --label Person
    """
    # parse the command line arguments
    args_parser = argparse.ArgumentParser()
    args_parser.add_argument(
        "--base_dir",
        type=str,
        required=True,
        help="path to the base output directory",
    )
    args_parser.add_argument(
        "--format",
        type=str,
        required=False,
        default="pascal",
        choices=["darknet", "coco", "kitti", "pascal", "tfrecord"],
        help="output format: KITTI, PASCAL, Darknet, TFRecord, or COCO",
    )
    args_parser.add_argument(
        "--label",
        type=str,
        required=True,
        nargs='+',
        help="object class to be fetched from OpenImages",
    )
    args_parser.add_argument(
        "--exclusions",
        type=str,
        required=False,
        help="path to file containing file IDs (one per line) to exclude from "
             "the final dataset",
    )
    args = vars(args_parser.parse_args())

    download_dataset(args["base_dir"], args["label"], args["format"], args["exclusions"])
