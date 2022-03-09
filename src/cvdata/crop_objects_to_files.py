import argparse
import os
import logging
import cv2
from cvdata.common import FORMAT_CHOICES
# ------------------------------------------------------------------------------
# set up a basic, global _logger which will write to the console
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d  %H:%M:%S",
)
_logger = logging.getLogger(__name__)


# ------------------------------------------------------------------------------

# ------------------------------------------------------------------------------
def crop_objects_to_files(
        images_dir: str,
        kitti_labels_dir: str,
        output_dir: str,
        image_ext: str,
):
    """
    
    """

    for annotation_file_name in os.listdir(kitti_labels_dir):
        anno_file_prefix ,_= os.path.splitext(annotation_file_name)
        image_file_name = anno_file_prefix +"."+image_ext
        image_file_path = os.path.join(images_dir, image_file_name)
        annotation_file_path = os.path.join(kitti_labels_dir, annotation_file_name)
        image = cv2.imread(image_file_path)
        with open(annotation_file_path, "r") as original_kitti_file:
            for line in original_kitti_file:
                parts = line.split(" ")
                class_name = parts[0]
                print(class_name)
                #left, top, right, bottom
                left,top= int(float(parts[4])), int(float(parts[5]))
                right,bottom= int(float(parts[6])), int(float(parts[7]))
                # y=rig_bot_y
                # x=top_left_x
                h=bottom - top
                w=right - left
                #crop_img = img[y:y+h, x:x+w]
                crop = image[top:top+h, left:left+w]
                
                #cv2.imshow('Image', crop)
                dest_class_folder =  os.path.join(output_dir,class_name)
                if(not os.path.exists(output_dir)):
                    os.mkdir(output_dir)
                if(not os.path.exists(dest_class_folder)):
                    os.mkdir(dest_class_folder)
                dest_object_image_file = os.path.join(dest_class_folder,class_name+"_"+anno_file_prefix+"_"+str(left)+"_"+str(top))
                cv2.imwrite(dest_object_image_file+"."+image_ext, crop)



# ------------------------------------------------------------------------------
def main():
    # parse the command line arguments
    args_parser = argparse.ArgumentParser()
    args_parser.add_argument(
        "--annotations_dir",
        required=False,
        type=str,
        default="label_2",
        help="path to directory containing input annotation files to be cropped",
    )
    args_parser.add_argument(
        "--images_dir",
        required=False,
        type=str,
        default="image_2",
        help="path to directory containing input image files",
    )    
    args_parser.add_argument(
        "--image_ext",
        required=False,
        type=str,
        default="jpg",
        help="original kitti image file extention name, like jpg or png, the cropped new file will also has this extension name",
    )
    args_parser.add_argument(
        "--output_dir",
        required=False,
        type=str,
        default="classification",
        help="path to directory to save the cropped objects files",
    )
    args = vars(args_parser.parse_args())

    if args["annotations_dir"] is not None:
        crop_objects_to_files(
            os.path.join(os.path.dirname(__file__), args["images_dir"]),
            os.path.join(os.path.dirname(__file__), args["annotations_dir"]),
            os.path.join(os.path.dirname(__file__), args["output_dir"]),
            args["image_ext"]
        )
    else:
        raise ValueError("annotations_dir must be provided, and now only support kitti format.")


# ------------------------------------------------------------------------------
if __name__ == "__main__":
    # Usage: ONLY FOR kitti, crop from images based on kitti label files, and save sub objects to file
    #     # $ python crop_objects_to_files.py --annotations_dir ~/datasets/handgun/kitti \
    #     --images_dir ~/datasets/handgun/images \
    #     --image_ext jpg \
    #     --output_dir cropped_for_classification
    #

    main()
