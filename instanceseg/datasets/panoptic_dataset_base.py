import abc

from torch.utils import data

from instanceseg.utils.misc import value_as_string
from .runtime_transformations import GenericSequenceRuntimeDatasetTransformer


class PanopticDatasetBase(data.Dataset):
    __metaclass__ = abc.ABC
    void_val = 255  # default

    # __getitem__(self, index) enforced by data.Dataset
    # __len__(self) enforced by data.Dataset

    @property
    @abc.abstractmethod
    def labels_table(self):
        raise NotImplementedError

    @abc.abstractmethod
    def get_image_id(self, index):
        raise NotImplementedError

    @abc.abstractmethod
    def get_datapoint(self, index):
        raise NotImplementedError

    @property
    def image_id_list(self):
        """
        [image_id0, image_id1, ..., image_idN] where N is len(self)
        """
        return [self.get_image_id(index) for index in range(len(self))]

    @property
    def semantic_class_names(self):
        """
        If we changed the semantic subset, we have to account for that change in the semantic
        class name list.
        """
        return self.get_semantic_class_names_from_labels_table(self.labels_table, self.void_val)

    @staticmethod
    def get_semantic_class_names_from_labels_table(labels_table, void_val):
        return [l['name'] for l in labels_table if l['id'] != void_val]

    @property
    def n_semantic_classes(self):
        return len(self.semantic_class_names)


class TransformedPanopticDataset(PanopticDatasetBase):

    def __init__(self, raw_dataset: PanopticDatasetBase, raw_dataset_returns_images=False,
                 precomputed_file_transformation=None, runtime_transformation=None):
        """
        :param raw_dataset_returns_images: Set to false for standard datasets that load from
        files; set to true for
        synthetic datasets that directly return images and labels.
        """

        if raw_dataset_returns_images:
            assert precomputed_file_transformation is None, \
                'Cannot do precomputed file transformation on datasets of type \'images\' ' \
                '(generated on the fly).'
        self.raw_dataset_returns_images = raw_dataset_returns_images
        self.raw_dataset = raw_dataset
        self.precomputed_file_transformation = precomputed_file_transformation
        self.runtime_transformation = runtime_transformation
        self.should_use_precompute_transform = True
        self.should_use_runtime_transform = True

    def __len__(self):  # explicit
        return len(self.raw_dataset)

    def __getitem__(self, index):
        precomputed_file_transformation = self.precomputed_file_transformation if \
            self.should_use_precompute_transform else None
        runtime_transformation = self.runtime_transformation if \
            self.should_use_runtime_transform else None
        identifier = self.get_image_id(index)
        if not self.raw_dataset_returns_images:
            img, (sem_lbl, inst_lbl) = self.get_item_from_files(identifier,
                                                         precomputed_file_transformation)
        else:
            img, (sem_lbl, inst_lbl) = self.raw_dataset.__getitem__(index)
            assert precomputed_file_transformation is None, \
                'Cannot do precomputed file transformation on datasets of type \'images\' ' \
                '(generated on the fly).'
        if runtime_transformation is not None:
            img, (sem_lbl, inst_lbl) = runtime_transformation.transform(img, (sem_lbl, inst_lbl))

        return {
            'image_id': identifier,
            'image': img,
            'sem_lbl': sem_lbl,
            'inst_lbl': inst_lbl,
            'transformation_tag': self.transformation_tag
        }

    def get_image_file(self, index):
        if not self.raw_dataset_returns_images:
            identifier = self.raw_dataset.image_id_list[index]
            data_file = self.raw_dataset.files[identifier]  # files populated when raw_dataset was
                                                            # instantiated
        else:
            raise Exception(
                'Cannot get filename from raw dataset {}'.format(type(self.raw_dataset)))
        return data_file

    @property
    def labels_table(self):
        # Select labels from labels_table that belong to the subset of semantic classes
        original_labels_table = self.raw_dataset.labels_table
        if self.should_use_runtime_transform and self.runtime_transformation is not None:
            transformation_list = self.runtime_transformation.transformer_sequence if isinstance(
                self.runtime_transformation, GenericSequenceRuntimeDatasetTransformer) else \
                [self.runtime_transformation]
            labels_table = original_labels_table
            for transformer in transformation_list:
                if hasattr(transformer, 'transform_labels_table'):
                    labels_table = transformer.transform_labels_table(labels_table)

            return labels_table
        else:
            return original_labels_table

    def load_files(self, img_file, sem_lbl_file, inst_lbl_file):
        # often self.raw_dataset.load_files(?)
        raise NotImplementedError

    def get_item_from_files(self, identifier, precomputed_file_transformation=None):
        data_file = self.raw_dataset.files[
            identifier]  # files populated when raw_dataset was instantiated
        img_file, sem_lbl_file, inst_lbl_file = data_file['img'], data_file['sem_lbl'], data_file[
            'inst_lbl']

        # Get the right file
        if precomputed_file_transformation is not None:
            img_file, sem_lbl_file, inst_lbl_file = \
                precomputed_file_transformation.transform(img_file=img_file,
                                                          sem_lbl_file=sem_lbl_file,
                                                          inst_lbl_file=inst_lbl_file)

        # Run data through transformation
        img, lbl = self.load_files(img_file, sem_lbl_file, inst_lbl_file)
        return img, lbl

    @property
    def transformation_tag(self):
        return get_transformer_identifier_tag(self.precomputed_file_transformation,
                                              self.runtime_transformation)


def get_transformer_identifier_tag(precomputed_file_transformation, runtime_transformation):
    transformer_tag = ''
    for tr in [precomputed_file_transformation, runtime_transformation]:
        attributes = tr.get_attribute_items() if tr is not None else {}.items()
        transformer_tag += '__'.join(['{}-{}'.format(k, value_as_string(v)) for k, v in attributes])
    return transformer_tag
