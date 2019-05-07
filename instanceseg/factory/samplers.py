import os

from instanceseg.datasets import sampler, dataset_statistics


def get_configured_sampler(dataset, dataset_configured_for_stats, sequential, n_instances_range,
                           n_images, sem_cls_filter, instance_count_file):
    """
    dataset: the actual dataset you want to sample from in the end
    dataset_configured_for_stats: the dataset you want to compute stats from (to inform how you
        sample 'dataset') -- useful if you're going to get rid of semantic classes, etc. but want
        to still sample images that have them.
        If it matches dataset, just pass dataset in for this parameter as well.
    """
    if sem_cls_filter is None and n_instances_range is None and n_images is None:
        valid_indices = None  # 'all'
    elif sem_cls_filter is not None or n_instances_range is not None:
            assert dataset_configured_for_stats is not None, 'No default dataset provided.  ' \
                                                             'Cannot compute stats.'
            assert len(dataset_configured_for_stats) == len(dataset), \
                AssertionError('Bug here.  Assumed same set of images (untransformed).')

            if not os.path.isfile(instance_count_file):
                print('Generating file {}'.format(instance_count_file))
                stats = dataset_statistics.InstanceDatasetStatistics(dataset_configured_for_stats)
                stats.compute_statistics(filename_to_write_instance_counts=instance_count_file)
            else:
                print('Reading from instance counts file {}'.format(instance_count_file))
                stats = dataset_statistics.InstanceDatasetStatistics(
                    dataset_configured_for_stats, existing_instance_count_file=instance_count_file)
            valid_indices = stats.get_valid_indices(n_instances_range, sem_cls_filter, n_images)
    elif n_images is not None:
        valid_indices = dataset_statistics.subsample_n_images(n_original_images=len(
            dataset_configured_for_stats), n_images=n_images)
    else:
        raise NotImplementedError('We shouldn\'t get here with the set of configs I\'m aware '
                                  'of at the moment')

    my_sampler = sampler.sampler_factory(sequential, bool_index_subset=valid_indices)(dataset)
    if len(my_sampler) == 0:
        raise ValueError('length of sampler is 0; {} valid indices'.format(sum(valid_indices)))
    if n_images:
        try:
            assert len(my_sampler.indices) == n_images, \
                AssertionError('Specified {} images, but len(sampler) is {}.  '
                               'You may need to make n_images smaller. There were {} valid '
                               'indices.'.format(len(my_sampler.indices), n_images,
                                                 sum(valid_indices)))
        except:
            import ipdb; ipdb.set_trace()
            raise
    return my_sampler
