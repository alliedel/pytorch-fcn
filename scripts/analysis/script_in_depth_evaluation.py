import argparse
import os
import os.path as osp

import matplotlib.pyplot as plt
import numpy as np
import torch

import instanceseg.utils.display as display_pyutils
import instanceseg.utils.logs
import instanceseg.utils.script_setup
from instanceseg.analysis import distribution_assignments
from collections import OrderedDict

FIGSIZE = (10, 10)
DPI = 300


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--logdir', help='directory that contains the checkpoint and config', type=str, required=True)
    parser.add_argument('--gpu', '-g', help='gpu identifier (int)', type=int, default=0)
    parser.add_argument('--relative', help='should export relative positions?', type=bool, default=True)
    parser.add_argument('--absolute', help='should export absolute positions?', type=bool, default=True)
    parser.add_argument('--workspace', help='directory to write results to', type=bool, default=None)
    args = parser.parse_args()
    return args


COLORMAP = 'cubehelix'  # 'cubehelix', 'inferno', 'magma', 'viridis', 'gray'


def make_histogram_set(assigned_attributes, channel_names, split, attribute_name, use_subplots=True):
    colors = [display_pyutils.GOOD_COLOR_CYCLE[np.mod(i, len(display_pyutils.GOOD_COLOR_CYCLE))]
              for i in range(len(channel_names))]
    labels = channel_names
    density, global_bins, patches = display_pyutils.nanhistogram(
        assigned_attributes, bins=None,
        color=colors, label=labels, histtype='stepfilled')
    plt.figure(figsize=FIGSIZE)
    plt.clf()

    if use_subplots:
        R = len(channel_names)
        plt.subplot(R, 1, 1)
        axes_list = []
        labels = ['{} ({} instances)'.format(channel_names[channel_idx], len(assigned_attributes[channel_idx])) for
                  channel_idx in range(len(channel_names))]
        for subplot_idx, channel_idx in enumerate(range(len(channel_names))):
            ax = plt.subplot(R, 1, subplot_idx + 1)
            axes_list.append(ax)
            y = assigned_attributes[channel_idx]
            channel_name = channel_names[channel_idx]
            bins = np.linspace(global_bins[0], global_bins[-1], 100)
            label = labels[subplot_idx]
            density, bins, patches = display_pyutils.nanhistogram(y, bins=bins, color=colors[subplot_idx],
                                                                  label=label, histtype='stepfilled')
            # plt.legend(patches, labels, loc='center left', fontsize=8, bbox_to_anchor=(-0.02, 0.5))
            if subplot_idx == 0:
                title = '{}: {}'.format(split, attribute_name)
                plt.title(title, fontsize=16)
            # plt.legend(loc='center left', fontsize=8, bbox_to_anchor=(-0.02, 0.5))
            plt.xlabel('{} for assigned ground truth instances'.format(attribute_name), fontsize=12)
            plt.legend(loc='upper right', fontsize=16)
        display_pyutils.sync_axes(axes_list, axis='x')
        display_pyutils.sync_axes(axes_list, axis='y')
    else:
        bins = None
        density, bins, patches = display_pyutils.nanhistogram(assigned_attributes, bins=None,
                                                              color=colors, label=labels, histtype='bar')
        title = '{}: {}'.format(split, attribute_name)
        plt.xlabel('{} for assigned ground truth instances'.format(attribute_name), fontsize=12)
        plt.title(title, fontsize=16)
        plt.legend(loc='upper right', fontsize=16)
    plt.tight_layout(pad=1.2)
    filename = '{}_{}_distributions_{}.png'.format(split, attribute_name,
                                                   'subplots' if use_subplots else 'combined')
    display_pyutils.save_fig_to_workspace(filename)


def make_scatterplot_set(xs, ys, channel_names, split, x_attribute_name, y_attribute_name, use_subplots=True):
    colors = [display_pyutils.GOOD_COLOR_CYCLE[np.mod(i, len(display_pyutils.GOOD_COLOR_CYCLE))]
              for i in range(len(channel_names))]
    labels = channel_names
    plt.figure(figsize=FIGSIZE)
    plt.clf()

    if use_subplots:
        R = len(channel_names)
        plt.subplot(R, 1, 1)
        axes_list = []
        labels = ['{} ({} instances)'.format(channel_names[channel_idx], len(ys[channel_idx])) for
                  channel_idx in range(len(channel_names))]
        for subplot_idx, channel_idx in enumerate(range(len(channel_names))):
            ax = plt.subplot(R, 1, subplot_idx + 1)
            axes_list.append(ax)
            channel_name = channel_names[channel_idx]

            label = labels[subplot_idx]

            x = xs[channel_idx]
            y = ys[channel_idx]
            plt.scatter(x, y, label=label, color=colors[subplot_idx])

            # plt.legend(patches, labels, loc='center left', fontsize=8, bbox_to_anchor=(-0.02, 0.5))
            if subplot_idx == 0:
                title = '{}: {} vs. {}'.format(split, x_attribute_name, y_attribute_name)
                plt.title(title, fontsize=16)
            # plt.legend(loc='center left', fontsize=8, bbox_to_anchor=(-0.02, 0.5))
            plt.xlabel('{} for assigned ground truth instances'.format(x_attribute_name), fontsize=12)
            plt.ylabel('{}'.format(y_attribute_name), fontsize=12)
            plt.legend(loc='upper right', fontsize=16)
        display_pyutils.sync_axes(axes_list, axis='x')
        display_pyutils.sync_axes(axes_list, axis='y')
    else:
        plt.hold(True)
        for channel_idx in range(len(channel_names)):
            x = xs[channel_idx]
            y = ys[channel_idx]
            label = labels[channel_idx]
            plt.scatter(x, y, label=label, color=colors[channel_idx])
        title = '{}: {} vs. {}'.format(split, x_attribute_name, y_attribute_name)
        plt.xlabel('{} for assigned ground truth instances'.format(x_attribute_name), fontsize=12)
        plt.ylabel('{}'.format(y_attribute_name), fontsize=12)
        plt.title(title, fontsize=16)
        plt.legend(loc='upper right', fontsize=16)
    plt.tight_layout(pad=1.2)
    filename = '{}_scatter2_x_{}_y_{}_{}.png'.format(
        split, x_attribute_name, y_attribute_name, 'subplots' if use_subplots else 'combined')
    display_pyutils.save_fig_to_workspace(filename)


def make_scatterplot3d_set(xs, ys, zs, channel_names, split, x_attribute_name, y_attribute_name,
                           z_attribute_name, use_subplots=True):
    colors = [display_pyutils.GOOD_COLOR_CYCLE[np.mod(i, len(display_pyutils.GOOD_COLOR_CYCLE))]
              for i in range(len(channel_names))]
    labels = channel_names
    plt.figure(figsize=FIGSIZE)
    plt.clf()

    if use_subplots:
        R = len(channel_names)
        plt.subplot(R, 1, 1)
        axes_list = []
        labels = ['{} ({} instances)'.format(channel_names[channel_idx], len(ys[channel_idx])) for
                  channel_idx in range(len(channel_names))]
        for subplot_idx, channel_idx in enumerate(range(len(channel_names))):
            ax = plt.subplot(R, 1, subplot_idx + 1)
            axes_list.append(ax)
            channel_name = channel_names[channel_idx]

            label = labels[subplot_idx]

            x = xs[channel_idx]
            y = ys[channel_idx]
            z = zs[channel_idx]
            display_pyutils.scatter3(x, y, z, zdir='z', label=label, color=colors[subplot_idx])

            # plt.legend(patches, labels, loc='center left', fontsize=8, bbox_to_anchor=(-0.02, 0.5))
            if subplot_idx == 0:
                title = '{}: {} vs. {}'.format(split, x_attribute_name, y_attribute_name)
                plt.title(title, fontsize=16)
            # plt.legend(loc='center left', fontsize=8, bbox_to_anchor=(-0.02, 0.5))
            plt.xlabel('{} for assigned ground truth instances'.format(x_attribute_name), fontsize=12)
            plt.ylabel('{}'.format(y_attribute_name), fontsize=12)
            plt.legend(loc='upper right', fontsize=16)
        display_pyutils.sync_axes(axes_list, axis='x')
        display_pyutils.sync_axes(axes_list, axis='y')
    else:
        plt.hold(True)
        for channel_idx in range(len(channel_names)):
            label = labels[channel_idx]
            x = xs[channel_idx]
            y = ys[channel_idx]
            z = zs[channel_idx]
            display_pyutils.scatter3(x, y, z, zdir='z', label=label, color=colors[channel_idx])
            plt.scatter(x, y, label=label, color=colors[channel_idx])
        title = '{}: {} vs. {}'.format(split, x_attribute_name, y_attribute_name)
        plt.xlabel('{} for assigned ground truth instances'.format(x_attribute_name), fontsize=12)
        plt.ylabel('{}'.format(y_attribute_name), fontsize=12)
        plt.title(title, fontsize=16)
        plt.legend(loc='upper right', fontsize=16)
    plt.tight_layout(pad=1.2)
    filename = '{}_scatter3_x_{}_y_{}_z_{}_{}.png'.format(
        split, x_attribute_name, y_attribute_name, z_attribute_name, 'subplots' if use_subplots else 'combined')
    display_pyutils.save_fig_to_workspace(filename)


def main():
    args = parse_args()
    logdir = args.logdir
    instanceseg.utils.script_setup.set_random_seeds()
    display_pyutils.set_my_rc_defaults()
    gpu = args.gpu
    os.environ['CUDA_VISIBLE_DEVICES'] = str(gpu) if isinstance(gpu, int) else ','.join(str(gpu))
    cuda = torch.cuda.is_available()
    if display_pyutils.check_for_emptied_workspace():
        print('Workspace clean.')
    else:
        print('Workspace not clean, but running anyway.')

    # Load directory
    cfg, model_pth, out_dir, problem_config, model, my_trainer, optim, dataloaders = \
        instanceseg.utils.logs.load_everything_from_logdir(logdir, gpu=args.gpu, packed_as_dict=False)
    model.eval()

    # Write log directory name to folder
    with open(osp.join(display_pyutils.WORKSPACE_DIR, osp.basename(osp.normpath(logdir))), 'w') as fid:
        fid.write(logdir)

    if cfg['augment_semantic']:
        raise NotImplementedError('Gotta augment semantic first before running through model.')

    # Display histograms of assigned instance sizes
    channel_names = problem_config.get_channel_labels()
    display_pyutils.set_my_rc_defaults()

    for split in ['train', 'val']:
        # NOTE(allie): At the moment, clims is not synced.  Need to get the min/max and pass them in.
        assigned_instance_sizes_2d, xent_losses_by_channel_2d, ious_by_channel_2d, soft_iou_loss_by_channel_2d = \
            distribution_assignments.get_per_channel_per_image_sizes_and_losses(
                model, dataloaders[split], cuda, my_trainer)
        soft_ious_by_channel_2d = 1.0 - soft_iou_loss_by_channel_2d
        diff_soft_iou_hard_iou_2d = ious_by_channel_2d - soft_ious_by_channel_2d

        for sem_cls_val in range(len(problem_config.semantic_class_names)):
            sem_cls_name = problem_config.semantic_class_names[sem_cls_val]
            if sem_cls_name == 'background':
                continue
            sem_cls_channel_idxs = [i for i, s_val in enumerate(problem_config.model_channel_semantic_ids)
                                    if s_val == sem_cls_val]
            sem_cls_channel_names = [channel_names[c] for c in sem_cls_channel_idxs]

            plt.figure(0)
            plt.clf()

            print('{} instances < 10 pixels'.format((assigned_instance_sizes_2d < 10).sum()))
            attributes_by_channel = OrderedDict([(name, convert_arr_to_nested_list_without_zeros(
                metric_2d, zeros_reference_array=assigned_instance_sizes_2d)) for name, metric_2d in
                                                 [
                                                 ('instance_size', assigned_instance_sizes_2d),
                                                 ('iou', ious_by_channel_2d),
                                                 ('soft_iou', soft_ious_by_channel_2d),
                                                 ('soft_iou_loss', soft_iou_loss_by_channel_2d),
                                                 ('diff_soft_iou_hard_iou', diff_soft_iou_hard_iou_2d),
                                                 ('xent_loss_contribution', xent_losses_by_channel_2d)
                                                ]]
            )

            # iou values
            for i, x_attribute_name in enumerate(attributes_by_channel.keys()):
                x = attributes_by_channel[x_attribute_name]
                for y_attribute_name in [k for j, k in enumerate(attributes_by_channel.keys()) if j > i]:
                    print(sem_cls_name, x_attribute_name, y_attribute_name)
                    y = attributes_by_channel[y_attribute_name]
                    for use_subplots in [False]:  # [True, False]:
                        make_scatterplot_set([x[c] for c in sem_cls_channel_idxs],
                                             [y[c] for c in sem_cls_channel_idxs], sem_cls_channel_names, split,
                                             x_attribute_name='{}_{}'.format(x_attribute_name, sem_cls_name),
                                             y_attribute_name='{}_{}'.format(y_attribute_name, sem_cls_name),
                                             use_subplots=use_subplots)

            # # Instance sizes
            # generate_instance_size_analysis(assigned_instance_sizes, assigned_instance_sizes_2d, sem_cls_channel_idxs,
            #                                 sem_cls_channel_names, split, sem_cls_name)


def generate_instance_size_analysis(assigned_instance_sizes, assigned_instance_sizes_2d, sem_cls_channel_idxs,
                                    sem_cls_channel_names, split, sem_cls_name):
    sorted_order = np.argsort(assigned_instance_sizes_2d[:, sem_cls_channel_idxs], axis=1).argsort(axis=1)
    num_zeros = (assigned_instance_sizes_2d[:, sem_cls_channel_idxs] == 0).sum(axis=1)
    # shifted_down
    assigned_instance_size_orders_2d = sorted_order - num_zeros.reshape((-1, 1)) + 1
    assigned_instance_size_orders_2d[assigned_instance_size_orders_2d < 0] = 0
    assigned_instance_size_orders_2d_down = assigned_instance_size_orders_2d.copy()
    # shifted up
    assigned_instance_size_orders_2d = sorted_order + 1
    assigned_instance_size_orders_2d[assigned_instance_size_orders_2d <= num_zeros.reshape((-1, 1))] = 0
    assigned_instance_size_orders_2d_up = assigned_instance_size_orders_2d.copy()
    # import ipdb; ipdb.set_trace()
    assigned_instance_size_orders_down = [assigned_instance_size_orders_2d_down[:, i]
                                          for i in range(assigned_instance_size_orders_2d_down.shape[1])]
    assigned_instance_size_orders_up = [assigned_instance_size_orders_2d_up[:, i]
                                        for i in range(assigned_instance_size_orders_2d_up.shape[1])]
    for subplots in [True, False]:
        make_histogram_set([assigned_instance_sizes[c] for c in sem_cls_channel_idxs],
                           sem_cls_channel_names, split,
                           attribute_name='instance_size_pixels_{}'.format(sem_cls_name), use_subplots=subplots)
        make_histogram_set(assigned_instance_size_orders_down, sem_cls_channel_names, split,
                           attribute_name='instance_size_order_shifted_down_{}'.format(sem_cls_name),
                           use_subplots=subplots)
        make_histogram_set(assigned_instance_size_orders_up, sem_cls_channel_names,
                           split, attribute_name='instance_size_order_shifted_up_{}'.format(sem_cls_name),
                           use_subplots=subplots)


def convert_arr_to_nested_list_without_zeros(assigned_instance_sizes_2d, zeros_reference_array=None):
    if zeros_reference_array is None:
        zeros_reference_array = assigned_instance_sizes_2d
    assigned_instance_sizes = [assigned_instance_sizes_2d[:, i] for i in range(assigned_instance_sizes_2d.shape[1])]
    for i in range(len(assigned_instance_sizes)):
        assigned_instance_sizes[i] = assigned_instance_sizes[i][zeros_reference_array[:, i] > 0]
    return assigned_instance_sizes


if __name__ == '__main__':
    main()
