import argparse
import os

from cvdata.common import FORMAT_CHOICES


# ------------------------------------------------------------------------------
def rename_image_files(
        images_dir: str,
        kitti_labels_dir: str,
        keep_old_name: bool,
        prefix: str,
        start: int,
        digits: int,
):
    """
    Renames all images in a directory to <prefix>_<enumeration>.<original_ext>,
    with the enumeration portion starting at a designated number and with a
    specified number of digits width.

    :param images_dir: all image files within this directory will be renamed
    :param kitti_labels_dir: all label files within this directory will be renamed
    :param keep_old_name: original file name will be kept as a part of new name
    :param prefix: the prefix used for the new file names
    :param start: the number at which the enumeration portion of the new file
        names should begin
    :param digits: the number of digits (width) of the enumeration portion of the
        new file names
    """

    supported_extensions = ("gif", "jpg", "jpeg", "png",)
    current = start
    for image_file_name in os.listdir(images_dir):
        orignal_image_file_short_name, ext = os.path.splitext(image_file_name)
        if ext[1:].lower() in supported_extensions:
            if not keep_old_name:
                new_image_file_name = f"{prefix}_{str(current).zfill(digits)}{ext}"
            else:
                new_image_file_name = f"{prefix}_{str(current).zfill(digits)}_{orignal_image_file_short_name}{ext}"
            new_image_file_path = os.path.join(images_dir, new_image_file_name)
            original_image_file_path = os.path.join(images_dir, image_file_name)
            os.rename(original_image_file_path, new_image_file_path)
            original_label_file_name = os.path.join(kitti_labels_dir, f"{orignal_image_file_short_name}.txt")
            if os.path.exists(original_label_file_name):
                os.rename(original_label_file_name, os.path.join(kitti_labels_dir, f"{new_image_file_name}.txt"))
            current += 1


# ------------------------------------------------------------------------------
def main():
    # parse the command line arguments
    args_parser = argparse.ArgumentParser()
    args_parser.add_argument(
        "--annotations_dir",
        required=True,
        type=str,
        help="path to directory containing input annotation files to be converted",
    )
    args_parser.add_argument(
        "--images_dir",
        required=True,
        type=str,
        help="path to directory containing input image files",
    )
    args_parser.add_argument(
        "--keep_old_name",
        required=False,
        type=bool,
        default=True,
        help="original file name will be kept as a part of new name",
    )
    args_parser.add_argument(
        "--prefix",
        required=True,
        type=str,
        help="file name prefix",
    )
    args_parser.add_argument(
        "--kitti_ids_file",
        required=False,
        type=str,
        help="name of the file that contains the file IDs for a dataset with "
             "annotations in KITTI format",
    )
    args_parser.add_argument(
        "--digits",
        required=False,
        type=int,
        default=6,
        help="the number of digits in the enumeration portion of the resulting "
             "file names",
    )
    args_parser.add_argument(
        "--format",
        required=True,
        type=str,
        choices=FORMAT_CHOICES,
        help="format of the annotations, only support kitti",
    )
    args_parser.add_argument(
        "--start",
        required=False,
        type=int,
        default=0,
        help="initial number to use in the enumeration",
    )
    args = vars(args_parser.parse_args())

    if args["annotations_dir"] is not None:
        rename_image_files(
            args["images_dir"],
            args["annotations_dir"],
            args["keep-old-name"],
            args["prefix"],
            args["start"],
            args["digits"],
        )
    else:
        raise ValueError("annotations_dir must be provided, and now only support kitti format.")


# ------------------------------------------------------------------------------
if __name__ == "__main__":
    # Usage: ONLY FOR kitti, rename names of dataset files (images and annotations)
    # $ python rename.py --annotations_dir ~/datasets/handgun/kitti \
    #     --images_dir ~/datasets/handgun/images \
    #     --prefix handgun --start 100 --digits 6 \
    #     --format kitti --kitti_ids_file file_ids.txt
    #
    # Usage: rename names of image files (images only)
    # $ python rename.py --images_dir ~/datasets/handgun/images \
    #     --prefix handgun --start 100 --digits 6

    main()
