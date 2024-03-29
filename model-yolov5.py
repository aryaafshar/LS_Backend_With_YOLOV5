import os
import logging
import boto3
import io
import json
import torch
from ultralytics import YOLO


#from mmdet.apis import init_detector, inference_detector

from label_studio_ml.model import LabelStudioMLBase
from label_studio_ml.utils import get_image_size, \
    get_single_tag_keys, DATA_UNDEFINED_NAME
from label_studio_tools.core.utils.io import get_data_dir
from botocore.exceptions import ClientError
from urllib.parse import urlparse
import pandas as pd


logger = logging.getLogger(__name__)
LABEL_STUDIO_HOST = os.getenv('LABEL_STUDIO_HOST', 'http://192.168.100.20:8080')
LABEL_STUDIO_API_KEY = os.getenv('LABEL_STUDIO_API_KEY', 'you-label-studio-api-key')

class MyModel(LabelStudioMLBase):
    """Object detector based on https://github.com/open-mmlab/mmdetection"""

    def __init__(self, 
                 checkpoint_file=None,
                 image_dir=None,
                 labels_file=None, score_threshold=0.3, device='cpu', **kwargs):
        """
        Load MMDetection model from config and checkpoint into memory.
        (Check https://mmdetection.readthedocs.io/en/v1.2.0/GETTING_STARTED.html#high-level-apis-for-testing-images)

        Optionally set mappings from COCO classes to target labels
        :param config_file: Absolute path to MMDetection config file (e.g. /home/user/mmdetection/configs/faster_rcnn/faster_rcnn_r50_fpn_1x.py)
        :param checkpoint_file: Absolute path MMDetection checkpoint file (e.g. /home/user/mmdetection/checkpoints/faster_rcnn_r50_fpn_1x_20181010-3d1b3351.pth)
        :param image_dir: Directory where images are stored (should be used only in case you use direct file upload into Label Studio instead of URLs)
        :param labels_file: file with mappings from COCO labels to custom labels {"airplane": "Boeing"}
        :param score_threshold: score threshold to wipe out noisy results
        :param device: device (cpu, cuda:0, cuda:1, ...)
        :param kwargs: can contain endpoint_url in case of non amazon s3
        """
        super(MyModel, self).__init__(**kwargs)
        #config_file = config_file or os.environ['config_file']
        checkpoint_file = checkpoint_file or os.environ['checkpoint_file']
        #self.config_file = config_file
        self.checkpoint_file = checkpoint_file
        self.labels_file = labels_file
        self.endpoint_url = kwargs.get('endpoint_url')
        if self.endpoint_url:
            logger.info(f'Using s3 endpoint url {self.endpoint_url}')
        
        # default Label Studio image upload folder
        upload_dir = os.path.join(get_data_dir(), 'media', 'upload')
        self.image_dir = image_dir or upload_dir
        logger.debug(f'{self.__class__.__name__} reads images from {self.image_dir}')
        if self.labels_file and os.path.exists(self.labels_file):
            self.label_map = json_load(self.labels_file)
        else:
            self.label_map = {}

        self.from_name, self.to_name, self.value, self.labels_in_config = get_single_tag_keys(
            self.parsed_label_config, 'RectangleLabels', 'Image')
        schema = list(self.parsed_label_config.values())[0]
        self.labels_in_config = set(self.labels_in_config)

        # Collect label maps from `predicted_values="airplane,car"` attribute in <Label> tag
        self.labels_attrs = schema.get('labels_attrs')
        if self.labels_attrs:
            for label_name, label_attrs in self.labels_attrs.items():
                for predicted_value in label_attrs.get('predicted_values', '').split(','):
                    self.label_map[predicted_value] = label_name

        print('Load new model from: ', checkpoint_file)
        #self.model = YOLO(checkpoint_file)
        self.score_thresh = score_threshold

    def _get_image_url(self, task):
        image_url = task['data'].get(self.value) or task['data'].get(DATA_UNDEFINED_NAME)
        if image_url.startswith('s3://'):
            # presign s3 url
            r = urlparse(image_url, allow_fragments=False)
            bucket_name = r.netloc
            key = r.path.lstrip('/')
            client = boto3.client('s3', endpoint_url=self.endpoint_url)
            try:
                image_url = client.generate_presigned_url(
                    ClientMethod='get_object',
                    Params={'Bucket': bucket_name, 'Key': key}
                )
            except ClientError as exc:
                logger.warning(f'Can\'t generate presigned URL for {image_url}. Reason: {exc}')
        return image_url

    def predict(self, tasks, **kwargs):
        assert len(tasks) == 1
        task = tasks[0]
        
        image_url = self._get_image_url(task)
        image_path = self.get_local_path(image_url)
       
        print("*********************************************************************")
        print(image_path)
        model = torch.hub.load("ultralytics/yolov5", "yolov5s")
        model_results = model(image_path)
        print("*********************************************************************")
        print("*********************************************************************")
        model_results_numpy=model_results.xyxy[0].numpy()
        results = []
        all_scores = []
        img_width, img_height = get_image_size(image_path)
        output_label="person"
        for a in model_results_numpy:
          if a[5]==0:
            if a[4]>self.score_thresh:
              x, y, xmax, ymax =a[0],a[1],a[2],a[3]
              score=float(a[4])
            results.append({
                    'from_name': self.from_name,
                    'to_name': self.to_name,
                    'type': 'rectanglelabels',
                    'value': {
                        'rectanglelabels': [output_label],
                        'x': x / img_width * 100,
                        'y': y / img_height * 100,
                        'width': (xmax - x) / img_width * 100,
                        'height': (ymax - y) / img_height * 100
                    },
                    'score': score
                })
      
            all_scores.append(score)
        avg_score = sum(all_scores) / max(len(all_scores), 1)
        return [{
            'result': results,
            'score': avg_score
        }]

def download_tasks(self, project):
        """
        Download all labeled tasks from project using the Label Studio SDK.
        Read more about SDK here https://labelstud.io/sdk/
        :param project: project ID
        :return:
        """
        ls = label_studio_sdk.Client(LABEL_STUDIO_HOST, LABEL_STUDIO_API_KEY)
        project = ls.get_project(id=project)
        tasks = project.get_labeled_tasks()
        return tasks
def json_load(file, int_keys=False):
    with io.open(file, encoding='utf8') as f:
        data = json.load(f)
        if int_keys:
            return {int(k): v for k, v in data.items()}
        else:
            return data
