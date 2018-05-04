import torch
import numpy as np
import scipy.misc
from torch.utils.data import sampler

# TODO(allie): Allow for augmentations

DEBUG_ASSERT = True


def sampler_factory(sequential, index_weights=None, bool_index_subset=None):
    """
    sequential: False -- will shuffle the images.  True -- will return the same order of images for each call
    weights: weights to assign to each image
    bool_filter: True for each index you'd like to include in the sampler
    """

    class SubsetWeightedSampler(sampler.Sampler):
        def __init__(self, initial_indices):
            self.initial_indices = initial_indices
            self.sequential = sequential
            self.indices = self.get_sample_indices_from_initial(self.initial_indices)

        def __iter__(self):
            if sequential:
                return iter(range(len(self.indices)))
            else:
                return iter(torch.randperm(len(self.indices)).long())

        @classmethod
        def get_sample_indices_from_initial(cls, initial_indices):
            if index_weights is not None:
                raise NotImplementedError
            if bool_index_subset is not None:
                new_indices = [index for index in initial_indices if bool_index_subset[index]]
            else:
                new_indices = initial_indices
            return new_indices
    return SubsetWeightedSampler


# class SubsetRandomSampler(sampler.Sampler):
#     r"""Samples elements randomly from a given list of indices, without replacement.
#
#     Arguments:
#         indices (list): a list of indices
#     """
#
#     def __init__(self, indices):
#         self.indices = indices
#
#     def __iter__(self):
#         return (self.indices[i] for i in torch.randperm(len(self.indices)))
#
#     def __len__(self):
#         return len(self.indices)
#
#
#
# class WeightedRandomSampler(sampler.Sampler):
#     r"""Samples elements from [0,..,len(weights)-1] with given probabilities (weights).
#
#     Arguments:
#         weights (list)   : a list of weights, not necessary summing up to one
#         num_samples (int): number of samples to draw
#         replacement (bool): if ``True``, samples are drawn with replacement.
#             If not, they are drawn without replacement, which means that when a
#             sample index is drawn for a row, it cannot be drawn again for that row.
#     """
#
#     def __init__(self, weights, num_samples, replacement=True):
#         if not isinstance(num_samples, _int_classes) or isinstance(num_samples, bool) or \
#                 num_samples <= 0:
#             raise ValueError("num_samples should be a positive integeral "
#                              "value, but got num_samples={}".format(num_samples))
#         if not isinstance(replacement, bool):
#             raise ValueError("replacement should be a boolean value, but got "
#                              "replacement={}".format(replacement))
#         self.weights = torch.tensor(weights, dtype=torch.double)
#         self.num_samples = num_samples
#         self.replacement = replacement
#
#     def __iter__(self):
#         return iter(torch.multinomial(self.weights, self.num_samples, self.replacement))
#
#     def __len__(self):
#         return self.num_samples


def assert_validation_images_arent_in_training_set(train_loader, val_loader):
    for val_idx, (val_img, _) in enumerate(val_loader):
        for train_idx, (train_img, _) in enumerate(train_loader):
            if np.allclose(train_img.numpy(), val_img.numpy()):
                import ipdb; ipdb.set_trace()
                raise Exception('validation img {} appears as training img {}'.format(val_idx,
                                                                                      train_idx))


def transform_lbl(lbl, resized_sz=None):
    # Resizing is tricky (we may lose classes to sub-pixel downsample)
    if resized_sz is not None:
        lbl = lbl.astype(float)
        lbl = scipy.misc.imresize(lbl, (resized_sz[0], resized_sz[1]), 'nearest', mode='F')

    lbl = torch.from_numpy(lbl).long()  # NOTE(allie): lbl.float() (?)
    return lbl


def transform_img(img, mean_bgr=None, resized_sz=None):
    img = img[:, :, ::-1]  # RGB -> BGR
    if resized_sz is not None:
        img = scipy.misc.imresize(img, (resized_sz[0], resized_sz[1]))
    img = img.astype(np.float64)
    if mean_bgr is not None:
        img -= mean_bgr
    # NHWC -> NCWH
    img = img.transpose(2, 0, 1)
    img = torch.from_numpy(img).float()
    return img


def untransform_lbl(lbl):
    lbl = lbl.numpy()
    return lbl


def untransform_img(img, mean_bgr=None, original_size=None):
    if original_size is not None:
        raise NotImplementedError
    img = img.numpy()
    img = img.transpose(1, 2, 0)
    if mean_bgr is not None:
        img += mean_bgr
    img = img.astype(np.uint8)
    img = img[:, :, ::-1]
    return img


def zeros_like(x, out_size=None):
    assert x.__class__.__name__.find('Variable') != -1 \
           or x.__class__.__name__.find('Tensor') != -1, "Object is neither a Tensor nor a Variable"
    if out_size is None:
        out_size = x.size()
    y = torch.zeros(out_size)
    if x.is_cuda:
        y = y.cuda()

    if x.__class__.__name__ == 'Variable':
        return torch.autograd.Variable(y, requires_grad=x.requires_grad)
    elif x.__class__.__name__.find('Tensor') != -1:
        return torch.zeros(y)


def labels_to_one_hot(input_labels, n_classes, output_onehot=None):
    """
    input_labels: either HxW or NxHxW
    output_onehot: either CxHxW or NxCxHxW depending on input_labels
    """
    void_class = 1  # If void class could exist (-1), we'll leave room for it and then remove it.
    ndims = len(input_labels.size())

    if output_onehot is None:
        if ndims == 2:
            out_size = (n_classes + void_class, input_labels.size(0), input_labels.size(1))
        elif ndims == 3:
            out_size = (input_labels.size(0), n_classes + void_class, input_labels.size(1),
                        input_labels.size(2))
        else:
            raise ValueError('input_labels should be HxW or NxHxW')
        output_onehot = zeros_like(input_labels, out_size=out_size)
    else:
        output_onehot = output_onehot.zero_()
    if ndims == 2:
        channel_dim = 0
        input_labels_expanded = input_labels[torch.np.newaxis, :, :] + void_class
    else:  # ndims == 3:
        channel_dim = 1
        input_labels_expanded = input_labels[:, torch.np.newaxis, :, :] + void_class
    try:
        output_onehot.scatter_(channel_dim, input_labels_expanded, 1)
    except:
        import ipdb; ipdb.set_trace()
        raise
    if ndims == 2:
        output_onehot = output_onehot[void_class:, :, :]
    else:
        output_onehot = output_onehot[:, void_class:, :, :]

    return output_onehot


def permute_instance_order(inst_lbl, n_max_per_class):
    for old_val, new_val in enumerate(np.random.permutation(range(n_max_per_class))):
        inst_lbl[inst_lbl == old_val] = new_val
    return inst_lbl


def remap_to_reduced_semantic_classes(lbl, reduced_class_idxs, map_other_classes_to_bground=True):
    """
    reduced_class_idxs = idxs_into_all_voc
    """
    # Make sure all lbl classes can be mapped appropriately.
    if not map_other_classes_to_bground:
        original_classes_in_this_img = [i for i in range(lbl.min(), lbl.max() + 1)
                                        if torch.sum(lbl == i) > 0]
        bool_unique_class_in_reduced_classes = [lbl_cls in reduced_class_idxs
                                                for lbl_cls in original_classes_in_this_img
                                                if lbl_cls != -1]
        if not all(bool_unique_class_in_reduced_classes):
            print(bool_unique_class_in_reduced_classes)
            import ipdb;
            ipdb.set_trace()
            raise Exception('Image has class labels outside the subset.\n Subset: {}\n'
                            'Classes in the image:{}'.format(reduced_class_idxs,
                                                             original_classes_in_this_img))
    if torch.is_tensor(lbl):
        old_lbl = lbl.clone()
    else:
        old_lbl = lbl.copy()
    lbl[...] = 0
    lbl[old_lbl == -1] = -1
    for new_idx, old_class_idx in enumerate(reduced_class_idxs):
        lbl[old_lbl == old_class_idx] = new_idx
    return lbl


def get_semantic_names_and_idxs(semantic_subset, full_set):
    """
    For VOC, full_set = voc.ALL_VOC_CLASS_NAMES
    """
    if semantic_subset is None:
        names = full_set
        idxs_into_all_voc = range(len(full_set))
    else:
        idx_name_tuples = [(idx, cls) for idx, cls in enumerate(full_set)
                           if cls in semantic_subset]
        idxs_into_all_voc = [tup[0] for tup in idx_name_tuples]
        names = [tup[1] for tup in idx_name_tuples]
        if 'background' not in names or 0 in names:
            print(Warning('Background is not included in the list of classes...'))
        if len(idxs_into_all_voc) != len(semantic_subset):
            unrecognized_class_names = [cls for cls in semantic_subset if cls not in names]
            raise Exception('unrecognized class name(s): {}'.format(unrecognized_class_names))
    return names, idxs_into_all_voc


def pytorch_unique(pytorch_1d_tensor):
    if torch.is_tensor(pytorch_1d_tensor):
        unique_labels = []
        for sem_l in pytorch_1d_tensor:
            if sem_l not in unique_labels:
                unique_labels.append(sem_l)
        return pytorch_1d_tensor.type(unique_labels)
    else:
        raise Exception('pytorch_1d_tensor isn\'t actually a tensor!  Maybe you want to use '
                        'local_pyutils.unique() for a list or np.unique() for a np array.')
