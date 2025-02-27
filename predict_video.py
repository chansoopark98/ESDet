from tensorflow.keras.applications.imagenet_utils import preprocess_input
from model.model_builder import ModelBuilder
from utils.misc import draw_bounding, CLASSES, COCO_CLASSES
from utils.model_post_processing import post_process
from utils.priors import *
import tensorflow as tf
import argparse
import glob
import cv2
import os

parser = argparse.ArgumentParser()
parser.add_argument("--backbone_name",       type=str,    help="Pretrained backbone name\
                                                            |   model_name    : description | \
                                                            [ 1. mobilenetv2       : MobileNetV2 ]\
                                                            [ 2. mobilenetv3s      : MobileNetV3-Small ] \
                                                            [ 3. mobilenetv3l      : MobileNetV3-Large ] \
                                                            [ 4. efficient_lite_v0 : EfficientNet-Lite-B0 ]\
                                                            [ 5. efficientnetv2b0  : EfficientNet-V2-B0 ]\
                                                            [ 6. efficientnetv2b3  : EfficientNet-V2-B3 ]",
                    default='efficient_lite_v0')
parser.add_argument("--num_classes",         type=int,    help="Number of classes in the pretrained model",
                    default=2)
parser.add_argument("--image_norm_type",     type=str,    help="Set RGB image nornalize format (tf or torch or no)\
                                                             [ 1. tf    : Rescaling RGB image -1 ~ 1 from imageNet ]\
                                                             [ 2. torch : Rescaling RGB image 0 ~ 1 from imageNet ]\
                                                             [ 3. else  : Rescaling RGB image 0 ~ 1 only divide 255 ]",
                    default='div')
parser.add_argument("--image_size",          type=tuple,  help="Model image size (input resolution)",
                    default=(300, 300))
parser.add_argument("--threshold",           type=float,  help="Post processing confidence threshold",
                    default=0.5)
parser.add_argument("--checkpoint_dir",      type=str,    help="Setting the model storage directory",
                    default='./checkpoints/')
parser.add_argument("--weight_name",         type=str,    help="Saved model weights directory",
                    default='your_model_weights.h5')
parser.add_argument("--gpu_num",             type=int,    help="Set GPU number to use(When without distribute training)",
                    default=0)
parser.add_argument("--video_dir",           type=str,    help="Path where the video is stored",
                    default='your_video_path/')
parser.add_argument("--video_type",          type=str,    help="Format of the saved video (e.g. mp4)",
                    default='mp4')
parser.add_argument("--video_result_dir",    type=str,    help="Video path to store inference results",
                    default='video_results/')
args = parser.parse_args()

if __name__ == '__main__':
    tf.config.set_soft_device_placement(True)

    os.makedirs(args.video_result_dir, exist_ok=True)

    video_list = os.path.join(args.video_dir, '*.' + args.video_type)
    video_list = glob.glob(video_list)

    if args.num_classes == 21:
        # PASCAL VOC
        label_list = CLASSES

    elif args.num_classes == 81:
        # COCO2017
        label_list = COCO_CLASSES
    else:
        # Custom dataset ('0', '1', '2', '3' ...)
        custom_label_list = range(args.num_classes)
        label_list = [str(label_iter) for label_iter in custom_label_list]

    gpu_number = '/device:GPU:' + str(args.gpu_num)
    with tf.device(gpu_number):


        # Set target transforms
        spec_list = convert_spec_list()
        priors = create_priors_boxes(specs=spec_list, image_size=args.image_size[0], clamp=True)
        target_transform = MatchingPriors(priors, center_variance, size_variance, iou_threshold)

        model = ModelBuilder(image_size=args.image_size, num_classes=args.num_classes).build_model(args.backbone_name)
        model.load_weights(args.checkpoint_dir + args.weight_name)
        model.summary()


        for video_idx, video_file in enumerate(video_list):
            video_idx += 1

            if os.path.isfile(video_file):	
                cap = cv2.VideoCapture(video_file)
            else:
                raise('cannot find file : {0}'.format(video_file))

            # Get camera FPS
            fps = cap.get(cv2.CAP_PROP_FPS)
            fps = 30
            # Frame width size
            frameWidth = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            # Frame height size
            frameHeight = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            frame_size = (frameWidth, frameHeight)
            print('frame_size={0}'.format(frame_size))
            
            video_name = args.video_result_dir + str(video_idx) + '.mp4'
            fourcc = cv2.VideoWriter_fourcc(*'XVID')
            video_writer = cv2.VideoWriter(video_name , fourcc, fps, frame_size)

            frame_idx = 0
            while True:
                print(frame_idx)
                retval, frame = cap.read()

                frame_idx+=1

                if not(retval):
                    break
                
                original_frame_shape = frame.shape

                img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                img = tf.image.resize(img, size=args.image_size,
                        method=tf.image.ResizeMethod.BILINEAR)
                img = tf.cast(img, tf.float32)

                if args.image_norm_type == 'torch':
                    img = preprocess_input(img, mode='torch')
                elif args.image_norm_type == 'tf':
                    img = preprocess_input(img, mode='tf')
                else:
                    img /= 255
                
                img = tf.expand_dims(img, axis=0)

                pred = model.predict(img)

                predictions = post_process(pred, target_transform, classes=args.num_classes, confidence_threshold=args.threshold)
                
                pred_boxes, pred_scores, pred_labels = predictions[0]

                if pred_boxes.size > 0:
                    draw_bounding(frame, pred_boxes,  labels=pred_labels,  scores=pred_scores, img_size=frame.shape[:2], label_list=label_list)

                video_writer.write(frame)
            
            video_writer.release()
        
            if cap.isOpend():
                cap.release()