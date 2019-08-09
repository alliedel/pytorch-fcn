from glob import glob

import PIL.Image
import numpy as np
import os.path as osp

from instanceseg.datasets.instance_dataset import InstanceDatasetBase, TransformedInstanceDataset
from instanceseg.datasets.precomputed_file_transformations import \
    GenericSequencePrecomputedDatasetFileTransformer
from . import labels_table_cityscapes
from .cityscapes_transformations import CityscapesMapRawtoTrainIdPrecomputedFileDatasetTransformer, \
    ConvertLblstoPModePILImages

CITYSCAPES_MEAN_BGR = np.array([73.15835921, 82.90891754, 72.39239876])


def get_default_cityscapes_root():
    other_options = [osp.abspath(osp.expanduser(p))
                     for p in ['~/afs_directories/kalman/data/cityscapes/']]
    cityscapes_root = osp.realpath(osp.abspath(osp.expanduser('data/cityscapes/')))
    if not osp.isdir(cityscapes_root):
        for option in other_options:
            if osp.isdir(option):
                cityscapes_root = option
                break
    return cityscapes_root  # gets rid of symlinks


CITYSCAPES_ROOT = get_default_cityscapes_root()


class CityscapesWithOurBasicTrainIds(InstanceDatasetBase):
    precomputed_file_transformer = GenericSequencePrecomputedDatasetFileTransformer(
        [CityscapesMapRawtoTrainIdPrecomputedFileDatasetTransformer(),
         ConvertLblstoPModePILImages()])
    void_val = 255
    # class names by id (not trainId)
    original_semantic_class_names = [l['name'] for l in labels_table_cityscapes.CITYSCAPES_LABELS_TABLE]

    def __init__(self, root, split):
        """
        Root must have the following directory structure:
            leftImg8bit/
                <split>/
                    *leftImg8bit.png
            gtFine/
                <split>/
        """
        self.root = osp.expanduser(osp.realpath(root))
        self.split = split
        self.files = self.get_files()

    def __len__(self):
        return len(self.files)

    def __getitem__(self, index):
        data_file = self.files[index]
        img, lbl = load_cityscapes_files(data_file['img'], data_file['sem_lbl'],
                                         data_file['inst_lbl'])
        return img, lbl

    @property
    def labels_table(self):
        labels_table = None
        for transformer in self.precomputed_file_transformer.transformer_sequence:
            if hasattr(transformer, 'transform_labels_table'):
                labels_table = transformer.transform_labels_table(labels_table_cityscapes.CITYSCAPES_LABELS_TABLE)
        assert labels_table is not None, 'Specifically for this Cityscapes loader, we are expecting the train ID ' \
                                         'mapper to give us the labels_table'
        return labels_table

    def get_files(self):
        dataset_dir = self.root
        split = self.split
        orig_file_list = get_raw_cityscapes_files(dataset_dir, split)
        if self.precomputed_file_transformer is not None:
            file_list = []
            for i, data_files in enumerate(orig_file_list):
                img_file, sem_lbl_file, raw_inst_lbl_file = self.precomputed_file_transformer.transform(
                    img_file=data_files['img'],
                    sem_lbl_file=data_files['sem_lbl'],
                    inst_lbl_file=data_files['inst_lbl'])
                file_list.append({
                    'img': img_file,
                    'sem_lbl': sem_lbl_file,
                    'inst_lbl': raw_inst_lbl_file,
                })
        else:
            file_list = orig_file_list
        return file_list

    @property
    def semantic_class_names(self):
        return self.get_semantic_class_names()

    @classmethod
    def get_default_semantic_class_names(cls):
        """
        If we changed the semantic subset, we have to account for that change in the semantic
        class name list.
        """
        if cls.precomputed_file_transformer is not None:
            transformation_list = cls.precomputed_file_transformer.transformer_sequence \
                if isinstance(cls.precomputed_file_transformer,
                              GenericSequencePrecomputedDatasetFileTransformer) else \
                [cls.precomputed_file_transformer]
            semantic_class_names = cls.original_semantic_class_names
            for transformer in transformation_list:
                if hasattr(transformer, 'transform_semantic_class_names'):
                    semantic_class_names = transformer.transform_semantic_class_names(
                        semantic_class_names)
        else:
            semantic_class_names = cls.original_semantic_class_names
        assert AssertionError(
            'There must be a bug somewhere.  The first semantic class name should always be '
            'background.')
        return semantic_class_names

    def get_semantic_class_names(self):
        """
        If we changed the semantic subset, we have to account for that change in the semantic
        class name list.
        """
        if self.precomputed_file_transformer is not None:
            transformation_list = self.precomputed_file_transformer.transformer_sequence \
                if isinstance(self.precomputed_file_transformer,
                              GenericSequencePrecomputedDatasetFileTransformer) else \
                [self.precomputed_file_transformer]
            semantic_class_names = self.original_semantic_class_names
            for transformer in transformation_list:
                if hasattr(transformer, 'transform_semantic_class_names'):
                    semantic_class_names = transformer.transform_semantic_class_names(
                        semantic_class_names)
        else:
            semantic_class_names = self.original_semantic_class_names
        assert AssertionError(
            'There must be a bug somewhere.  The first semantic class name should always be '
            'background.')
        return semantic_class_names

    @property
    def n_semantic_classes(self):
        return len(self.semantic_class_names)


def get_raw_cityscapes_files(dataset_dir, split):
    files = []
    images_base = osp.join(dataset_dir, 'leftImg8bit', split)
    glob_regex = osp.join(images_base, '*', '*.png')
    images = sorted(glob(glob_regex))
    assert len(images) > 0, "No images found with {}".format(glob_regex)
    for index, img_file in enumerate(images):
        img_file = img_file.rstrip()
        sem_lbl_file = img_file.replace('leftImg8bit/', 'gtFine/').replace(
            'leftImg8bit.png', 'gtFine_labelIds.png')
        raw_inst_lbl_file = sem_lbl_file.replace('labelIds', 'instanceIds')
        assert osp.isfile(img_file), '{} does not exist'.format(img_file)
        assert osp.isfile(sem_lbl_file), '{} does not exist'.format(sem_lbl_file)
        assert osp.isfile(raw_inst_lbl_file), '{} does not exist'.format(raw_inst_lbl_file)

        files.append({
            'img': img_file,
            'sem_lbl': sem_lbl_file,
            'inst_lbl': raw_inst_lbl_file,
        })
    assert len(files) > 0
    return files


def load_cityscapes_files(img_file, sem_lbl_file, inst_lbl_file):
    img_loaded = PIL.Image.open(img_file)

    try:
        img = np.array(img_loaded, dtype=np.uint8)
    except:
        img = np.array(img_loaded, dtype=np.uint8)

    # load semantic label
    sem_lbl = np.array(PIL.Image.open(sem_lbl_file), dtype=np.int32)
    # load instance label
    inst_lbl = np.array(PIL.Image.open(inst_lbl_file), dtype=np.int32)
    img_loaded.close()
    return img, (sem_lbl, inst_lbl)


class TransformedCityscapes(TransformedInstanceDataset):
    """
    Has a raw dataset
    """

    def __init__(self, root, split, precomputed_file_transformation=None,
                 runtime_transformation=None):
        raw_dataset = CityscapesWithOurBasicTrainIds(root, split=split)
        super(TransformedCityscapes, self).__init__(
            raw_dataset=raw_dataset,
            raw_dataset_returns_images=False,
            precomputed_file_transformation=precomputed_file_transformation,
            runtime_transformation=runtime_transformation)

    def load_files(self, img_file, sem_lbl_file, inst_lbl_file):
        return load_cityscapes_files(img_file, sem_lbl_file, inst_lbl_file)
