import collections
import tqdm
from torch.autograd import Variable
import torch
import os.path
import torch.nn.functional as F
from torch.utils.data import sampler
from torchfcn import script_utils
from local_pyutils import flatten_dict


class InstanceMetrics(object):
    def __init__(self, problem_config, data_loader):
        self.problem_config = problem_config
        self.data_loader = data_loader
        assert not isinstance(self.data_loader.sampler, sampler.RandomSampler), \
            'Sampler is instance of RandomSampler. Please set shuffle to False on data_loader'
        assert isinstance(self.data_loader.sampler, sampler.SequentialSampler), NotImplementedError
        self.scores = None
        self.assignments = None
        self.softmaxed_scores = None
        self.n_pixels_assigned_per_channel = None
        self.n_instances_assigned_per_sem_cls = None
        self.n_found_per_sem_cls, self.n_missed_per_sem_cls, self.channels_of_majority_assignments = None, None, None
        self.metrics_computed = False

    def clear(self, variables_to_preserve=('problem_config', 'data_loader')):
        """
        Clear to evaluate a new model
        """
        for attr_name in self.__dict__.keys():
            if attr_name in variables_to_preserve:
                continue
            setattr(self, attr_name, None)

    def compute_metrics(self, model):
        scores = self.compute_scores(model)
        self.assignments = argmax_scores(scores)
        self.softmaxed_scores = softmax_scores(scores)
        self.n_pixels_assigned_per_channel = self._compute_pixels_assigned_per_channel(self.assignments)
        self.n_instances_assigned_per_sem_cls = \
            self._compute_instances_assigned_per_sem_cls(self.n_pixels_assigned_per_channel)
        self.n_found_per_sem_cls, self.n_missed_per_sem_cls, self.channels_of_majority_assignments = \
            self._compute_majority_assignment_stats(self.assignments)
        self.metrics_computed = True
        self.scores = scores

    def compute_scores(self, model):
        return self._compile_scores(model).data

    def _compile_scores(self, model):
        return compile_scores(model, self.data_loader)

    def _compute_pixels_assigned_per_channel(self, assignments):
        n_images = len(self.data_loader)
        n_inst_classes = len(self.problem_config.semantic_instance_class_list)
        n_pixels_assigned_per_channel = torch.IntTensor(n_images, n_inst_classes).zero_()
        for channel_idx, (sem_cls, inst_id) in enumerate(zip(self.problem_config.semantic_instance_class_list,
                                                             self.problem_config.instance_count_id_list)):
            n_pixels_assigned_per_channel[:, channel_idx] = \
                (assignments[:, :, :] == channel_idx).int().sum(dim=2).sum(dim=1)
        return n_pixels_assigned_per_channel

    def _compute_instances_assigned_per_sem_cls(self, pixels_assigned_per_channel):
        n_images = len(self.data_loader)
        instances_found_per_channel = torch.IntTensor(n_images, self.problem_config.n_semantic_classes).zero_()
        for channel_idx, (sem_cls, inst_id) in enumerate(zip(self.problem_config.semantic_instance_class_list,
                                                             self.problem_config.instance_count_id_list)):
            instances_found_per_channel[:, sem_cls] += (pixels_assigned_per_channel[:, channel_idx] > 0).int()
        return instances_found_per_channel

    def _compute_majority_assignment_stats(self, assignments, majority_fraction=0.5):
        n_images = len(self.data_loader)
        n_found_per_sem_cls = torch.IntTensor(n_images, self.problem_config.n_semantic_classes).zero_()
        n_missed_per_sem_cls = torch.IntTensor(n_images, self.problem_config.n_semantic_classes).zero_()
        channels_of_majority_assignments = \
            torch.IntTensor(n_images, len(self.problem_config.semantic_instance_class_list)).zero_()

        already_matched_pred_channels = torch.ByteTensor(len(self.problem_config.semantic_instance_class_list))
        assumed_image_size = (assignments.size(1), assignments.size(2))
        for data_idx, (_, (sem_lbl, inst_lbl)) in enumerate(self.data_loader):
            already_matched_pred_channels.zero_()
            for gt_channel_idx, (sem_cls, inst_id) in enumerate(zip(self.problem_config.semantic_instance_class_list,
                                                                    self.problem_config.instance_count_id_list)):
                instance_mask = (sem_lbl == sem_cls) * (inst_lbl == inst_id)
                if (instance_mask.size(1), instance_mask.size(2)) != assumed_image_size:
                    instance_mask = crop_to_reduced_size12(instance_mask, assumed_image_size)

                # Find majority assignment for this gt instance
                if instance_mask.sum() == 0:
                    continue
                instance_assignments = assignments[data_idx, :, :][instance_mask]
                try:
                    mode_as_torch_tensor = torch.mode(instance_assignments)[0]
                except:
                    import ipdb;
                    ipdb.set_trace()
                pred_channel_idx = mode_as_torch_tensor.numpy().item()  # mode returns (val, idx)
                if already_matched_pred_channels[pred_channel_idx]:
                    # We've already assigned this channel to an instance; can't double-count.
                    n_missed_per_sem_cls[data_idx, sem_cls] += 1
                else:
                    # Check whether the majority assignment comprises over half of the pixels
                    n_instance_pixels = instance_mask.float().sum()
                    n_pixels_assigned = (instance_assignments == pred_channel_idx).float().sum()
                    if n_pixels_assigned >= n_instance_pixels * majority_fraction:  # is_majority
                        n_found_per_sem_cls[data_idx, sem_cls] += 1
                        channels_of_majority_assignments[data_idx, pred_channel_idx] += 1
                        already_matched_pred_channels[pred_channel_idx] = True
                    else:
                        n_missed_per_sem_cls[data_idx, sem_cls] += 1
                        n_found_per_sem_cls[data_idx, sem_cls] += 1
        return n_found_per_sem_cls, n_missed_per_sem_cls, channels_of_majority_assignments

    def get_aggregated_metrics_as_nested_dict(self):
        """
        Aggregate metrics over images and return list of metrics to summarize the performance of the model.
        """
        assert self.metrics_computed, 'Run compute_metrics first'
        channel_labels = self.problem_config.get_channel_labels('{}_{}')
        sem_labels = self.problem_config.class_names
        sz_score_by_sem = self.softmaxed_scores.size()
        sz_score_by_sem[1] = self.problem_config.n_semantic_classes
        softmax_scores_per_sem_cls = torch.zeros(sz_score_by_sem)
        for sem_cls in range(self.problem_config.n_semantic_classes):
            chs = [ci for ci, sc in
                   enumerate(self.problem_config.semantic_instance_class_list) if sc == sem_cls]
            softmax_scores_per_sem_cls[:, sem_cls, ...] = self.softmaxed_scores[:, chs, ...].sum(dim=1)
        metrics_dict = {
            'n_instances_assigned_per_sem_cls':
                {
                    self.problem_config.class_names[sem_cls] + '_sum': self.n_instances_assigned_per_sem_cls[:,
                                                                       sem_cls].sum()
                    for sem_cls in range(self.n_instances_assigned_per_sem_cls.size(1))
                },
            'n_images_with_more_than_one_instance_assigned':
                {
                    self.problem_config.class_names[sem_cls] + '_sum':
                        (self.n_instances_assigned_per_sem_cls[:, sem_cls] > 1).sum()
                    for sem_cls in range(self.n_instances_assigned_per_sem_cls.size(1))
                },
            'channel_utilization':
                {
                    'assignment': {
                        'pixels':
                            {
                                channel_labels[channel_idx] + '_mean': torch.mean(
                                    (self.n_pixels_assigned_per_channel.float())[:, channel_idx])
                                for channel_idx in range(self.n_pixels_assigned_per_channel.size(1))
                            },
                        'instances':
                            {
                                channel_labels[channel_idx] + '_sum':
                                    self.channels_of_majority_assignments[:, channel_idx].sum()
                                for channel_idx in range(self.channels_of_majority_assignments.size(1))
                            },
                    },
                    #         inst_channel_keyname = 'channel_usage_fraction/{}'.format(channel_labels[inst_idx])
                    #         analytics[inst_channel_keyname] = pixels_assigned_to_me.int().sum() / \
                    #                                           pixels_assigned_to_my_sem_cls.int().sum()
                    'softmax_score': {
                        'value_for_assigned_pixels': {
                            channel_labels[channel_idx] + '_mean':
                                (self.softmaxed_scores[:, channel_idx, :, :][self.assignments == channel_idx]).mean()
                            for channel_idx in range(self.softmaxed_scores.size(1))
                        },
                        'fraction_of_sem_cls_for_assigned_pixels': {
                            channel_labels[channel_idx] + '_mean':
                                ((self.softmaxed_scores[:, channel_idx, :, :][self.assignments == channel_idx]) /
                                 self.softmaxed_scores[:, sem_cls, :, :][self.assignments == channel_idx]).mean()
                            for channel_idx, sem_cls in enumerate(self.problem_config.semantic_instance_class_list)
                        },
                    },
                },
            'perc_found_per_sem_cls':
                {
                    sem_labels[sem_cls] + '_mean': torch.mean(self.n_found_per_sem_cls[:, sem_cls].float() / (
                            self.n_found_per_sem_cls[:, sem_cls] + self.n_missed_per_sem_cls[:, sem_cls]).float())
                    for sem_cls in range(self.n_instances_assigned_per_sem_cls.size(1))
                },
            'n_found_per_sem_cls':
                {
                    sem_labels[sem_cls] + '_mean': torch.mean(self.n_found_per_sem_cls[:, sem_cls].float())
                    for sem_cls in range(self.n_instances_assigned_per_sem_cls.size(1))
                },
        }
        return metrics_dict

    def get_images_based_on_characteristics(self):
        image_characteristics = {
            'multiple_instances_detected':
                [n_instances > 1 for n_instances in self.n_instances_assigned_per_sem_cls.max(dim=1)[0]],
        }
        return image_characteristics


def get_same_sem_cls_channels(channel_idx, semantic_instance_class_list):
    return [ci for ci, sc in enumerate(semantic_instance_class_list)
            if sc == semantic_instance_class_list[channel_idx]]


def compile_scores(model, data_loader):
    training = model.training
    model.eval()
    compiled_scores = None
    n_images = data_loader.batch_size * len(data_loader)
    n_channels = model.n_classes
    batch_size = data_loader.batch_size
    min_image_size, max_image_size = (torch.np.inf, torch.np.inf), (0, 0)
    for batch_idx, (data, (sem_lbl, inst_lbl)) in tqdm.tqdm(
            enumerate(data_loader), total=len(data_loader), desc='Running dataset through model', ncols=80,
            leave=False):
        min_image_size = (min(min_image_size[0], data.size(2)), min(min_image_size[1], data.size(3)))
        max_image_size = (max(max_image_size[0], data.size(2)), min(max_image_size[1], data.size(3)))

    compiled_scores = Variable(torch.ones(n_images, n_channels, *list(min_image_size)))
    for batch_idx, (data, (sem_lbl, inst_lbl)) in tqdm.tqdm(
            enumerate(data_loader), total=len(data_loader), desc='Running dataset through model', ncols=80,
            leave=False):
        data, sem_lbl, inst_lbl = Variable(data, volatile=True), Variable(sem_lbl), Variable(inst_lbl)
        if next(model.parameters()).is_cuda:
            data, sem_lbl, inst_lbl = data.cuda(), sem_lbl.cuda(), inst_lbl.cuda()
        scores = model(data)
        if compiled_scores is None:
            compiled_scores = Variable(torch.ones(n_images, *list(scores.size())[1:]))
        try:
            compiled_scores[(batch_idx * batch_size):((batch_idx + 1) * batch_size), ...] = scores
        except:
            if all([s1 > s2 for s1, s2 in zip(
                    compiled_scores[(batch_idx * batch_size):((batch_idx + 1) * batch_size), ...].size(),
                    scores.size())]):
                import ipdb;
                ipdb.set_trace()
                raise
            else:
                # print(Warning('Cropping image from size {} to {} for easier analysis'.format(
                #     scores.size(), compiled_scores.size())))
                cropped_size = (compiled_scores.size(2), compiled_scores.size(3))
                cropped_scores = crop_to_reduced_size23(scores, cropped_size)
                try:
                    assert cropped_scores.size() == \
                           compiled_scores[(batch_idx * batch_size):((batch_idx + 1) * batch_size), ...].size()
                except:
                    import ipdb;
                    ipdb.set_trace()
                    raise
                compiled_scores[(batch_idx * batch_size):((batch_idx + 1) * batch_size), ...] = cropped_scores
    if training:
        model.train()
    return compiled_scores


def crop_to_reduced_size23(tensor, cropped_size23):
    assert len(tensor.size()) == 4, NotImplementedError
    try:
        start_coords = (int((tensor.size(2) - cropped_size23[0]) / 2),
                        int((tensor.size(3) - cropped_size23[1]) / 2))
        cropped_tensor = tensor[:, :,
                         start_coords[0]:(start_coords[0] + cropped_size23[0]),
                         start_coords[1]:(start_coords[1] + cropped_size23[1])]
        assert cropped_tensor.size()[2:] == cropped_size23
    except:
        import ipdb;
        ipdb.set_trace();
        raise
    return cropped_tensor


def crop_to_reduced_size12(tensor, cropped_size12):
    assert len(tensor.size()) == 3, NotImplementedError
    try:
        start_coords = (int((tensor.size(1) - cropped_size12[0]) / 2),
                        int((tensor.size(2) - cropped_size12[1]) / 2))
        cropped_tensor = tensor[:,
                         start_coords[0]:(start_coords[0] + cropped_size12[0]),
                         start_coords[1]:(start_coords[1] + cropped_size12[1])]
    except:
        import ipdb;
        ipdb.set_trace();
        raise
    return cropped_tensor


def softmax_scores(compiled_scores, dim=1):
    return F.softmax(Variable(compiled_scores), dim=dim).data


def argmax_scores(compiled_scores, dim=1):
    return compiled_scores.max(dim=dim)[1]


def _test():
    logdir = 'scripts/logs/synthetic/TIME-20180430-151222_VCS-b7e0570_MODEL-train_instances_' \
             'CFG-000_F_SEM-False_SSET-None_INIT_SEM-False_SM-None_VOID-True_MA-True_VAL-100_' \
             'DECAY-0.0005_SEM_LS-False_LR-0.0001_1INST-False_ITR-10000_NPER-None_OPTIM-sgd_MO-0.99_BCC-None_SA-True/'
    model_best_path = os.path.join(logdir, 'model_best.pth.tar')
    checkpoint = torch.load(model_best_path)
    gpu = 0
    os.environ['CUDA_VISIBLE_DEVICES'] = str(gpu)
    cuda = torch.cuda.is_available()

    cfg_file = os.path.join(logdir, 'config.yaml')
    cfg = script_utils.create_config_copy(script_utils.load_config(cfg_file), reverse_replacements=True)
    synthetic_generator_n_instances_per_semantic_id = 2
    n_instances_per_class = cfg['n_instances_per_class'] or \
                            (1 if cfg['single_instance'] else synthetic_generator_n_instances_per_semantic_id)

    dataloaders = script_utils.get_dataloaders(cfg, 'synthetic', cuda)
    problem_config = script_utils.get_problem_config(dataloaders['val'].dataset.class_names, n_instances_per_class)
    model, start_epoch, start_iteration = script_utils.get_model(cfg, problem_config, checkpoint,
                                                                 semantic_init=None, cuda=cuda)
    instance_metrics = InstanceMetrics(problem_config, dataloaders['val'])
    # not necessary, but we'll make sure it runs anyway
    instance_metrics.clear()
    instance_metrics.compute_metrics(model)
    metrics_as_nested_dict = instance_metrics.get_aggregated_metrics_as_nested_dict()
    metrics_as_flattened_dict = flatten_dict(metrics_as_nested_dict)
    instance_metrics.get_images_based_on_characteristics()
    instance_metrics.clear()


if __name__ == '__main__':
    _test()

#     analytics = {
#         'scores': {
#             'max': pred_scores_stacked.max(),
#             # 'mean': pred_scores_stacked.mean(),
#             # 'median': pred_scores_stacked.median(),
#             'min': pred_scores_stacked.min(),
#             # 'abs_mean': abs_scores_stacked.mean(),
#             'abs_median': abs_scores_stacked.median(),
#         },
#     }
#     for channel in range(pred_scores_stacked.size(1)):
#         channel_scores = pred_scores_stacked[:, channel, :, :]
#         abs_channel_scores = abs_scores_stacked[:, channel, :, :]
#         analytics['per_channel_scores/{}'.format(channel)] = {
#             'max': channel_scores.max(),
#             # 'mean': channel_scores.mean(),
#             # 'median': channel_scores.median(),
#             'min': channel_scores.min(),
#             # 'abs_mean': abs_channel_scores.mean(),
#             'abs_median': abs_channel_scores.median(),
#         }
#     channel_labels = self.instance_problem.get_channel_labels('{}_{}')
#     for inst_idx, sem_cls in enumerate(self.instance_problem.semantic_instance_class_list):
#         same_sem_cls_channels = [channel for channel, cls in enumerate(
#             self.instance_problem.semantic_instance_class_list) if cls == sem_cls]
#         all_maxes = softmax_scores[:, same_sem_cls_channels, :, :].max(dim=1)[0]
#         all_sums = softmax_scores[:, same_sem_cls_channels, :, :].sum(dim=1)
#         # get 'smearing' level across all channels
#         sem_channel_keyname = 'instance_commitment/{}'.format(self.instance_problem.class_names[sem_cls])
#         if sem_channel_keyname not in analytics.keys():
#             # first of its sem class -- run semantic analytics here
#             relevant_pixels = sem_label == sem_cls
#             import ipdb; ipdb.set_trace()
#             analytics[sem_channel_keyname] = \
#                 (all_maxes[relevant_pixels] / all_sums[relevant_pixels]).mean(),
#
#         # get 'commitment' level within each channel
#         pixels_assigned_to_me = (label_preds == inst_idx)
#         pixels_assigned_to_my_sem_cls = torch.sum([(label_preds == channel) for channel in
#                                                    same_sem_cls_channels])
#         # channel_usage_fraction: fraction of channels of same semantic class that are used
#         inst_channel_keyname = 'channel_usage_fraction/{}'.format(channel_labels[inst_idx])
#         analytics[inst_channel_keyname] = pixels_assigned_to_me.int().sum() / \
#                                           pixels_assigned_to_my_sem_cls.int().sum()
#
#     return analytics
#
