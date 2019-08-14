import argparse

import numpy as np
import os
import os.path as osp

from instanceseg.panoeval import compute
from instanceseg.panoeval.utils import collate_pq_into_pq_compute_per_imageNxS
from instanceseg.utils import instance_utils
from scripts import convert_test_results_to_coco

here = osp.dirname(osp.abspath(__file__))


def main_unwrapped(gt_json_file, pred_json_file, gt_folder, pred_folder, problem_config, iou_threshold=None,
                   overwrite=False):
    if iou_threshold is None:
        iou_threshold = 0.5
    if iou_threshold != 0.5:
        out_dirs_root = os.path.join(os.path.dirname(pred_json_file), 'iou_threshold_{}'.format(iou_threshold))
        if not os.path.exists(out_dirs_root):
            os.makedirs(out_dirs_root)
    else:
        out_dirs_root = os.path.dirname(pred_json_file)

    outfile_collated = os.path.join(out_dirs_root, 'collated_stats_per_img_per_cat.npz')
    if os.path.exists(outfile_collated) and not overwrite:
        print('Eval stats file already exists: {}'.format(outfile_collated))
        return outfile_collated
    print('Evaluating from {}, {}'.format(gt_json_file, pred_json_file))
    print('Evaluating from {}, {}'.format(gt_folder, pred_folder))
    class_avgs_per_image = compute.pq_compute_per_image(gt_json_file=gt_json_file, pred_json_file=pred_json_file,
                                                        gt_folder=gt_folder, pred_folder=pred_folder,
                                                        iou_threshold=iou_threshold)
    # isthing = problem_config.has_instances
    categories = problem_config.semantic_vals
    collated_stats_per_image_per_cat = collate_pq_into_pq_compute_per_imageNxS(class_avgs_per_image, categories)
    np.savez(outfile_collated,
             collated_stats_per_image_per_cat=collated_stats_per_image_per_cat,
             categories=categories, problem_config=problem_config, gt_json_file=gt_json_file,
             pred_json_file=pred_json_file, gt_folder=gt_folder, pred_folder=pred_folder,
             iou_threshold=iou_threshold)
    print('Stats (and categories/problem config) saved to {}'.format(outfile_collated))

    return outfile_collated


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('test_logdir', type=str, help="We can create the COCO panoptic format from the "
                                                      "directory here")
    parser.add_argument('--iou_threshold', type=float, default=0.5)
    args = parser.parse_args()
    return args


def get_paths_from_test_dir(cached_test_dir):
    gt_json_file = os.path.join(cached_test_dir, 'panoptic_conversion_gt.json')
    pred_json_file = os.path.join(cached_test_dir, 'panoptic_conversion_pred.json')
    gt_folder = gt_json_file.replace('.json', '')
    pred_folder = pred_json_file.replace('.json', '')
    problem_config_file = os.path.join(
        os.path.dirname(cached_test_dir.rstrip('/')).replace('cache/', 'scripts/logs/'),
        'instance_problem_config.yaml')
    assert os.path.exists(problem_config_file), \
        'Assumed problem config file does not exist: {}'.format(problem_config_file)
    return {
        'gt_json_file': gt_json_file,
        'gt_folder': gt_folder,
        'pred_folder': pred_folder,
        'problem_config_file': problem_config_file
    }


def main(test_logdir, iou_threshold=None, overwrite=False):
    problem_config_ = instance_utils.InstanceProblemConfig.load(
        os.path.join(test_logdir, 'instance_problem_config.yaml'))
    out_dirs_cache_root = convert_test_results_to_coco.get_cache_dir_from_test_logdir(test_logdir)
    out_jsons, out_dirs = convert_test_results_to_coco.main(
        os.path.join(test_logdir, 'predictions'), os.path.join(
            test_logdir, 'groundtruth'), problem_config_, out_dirs_cache_root, overwrite=overwrite)
    # files = get_paths_from_test_dir(out_dirs_cache_root)
    collated_stats_per_image_per_cat_file = main_unwrapped(gt_json_file=out_jsons['gt'],
                                                           pred_json_file=out_jsons['pred'],
                                                           gt_folder=out_dirs['gt'], pred_folder=out_dirs['pred'],
                                                           problem_config=problem_config_,
                                                           iou_threshold=iou_threshold, overwrite=overwrite)
    return collated_stats_per_image_per_cat_file


if __name__ == '__main__':
    args_ = parse_args()
    collated_stats_per_image_per_cat_file_ = main(args_.test_logdir, iou_threshold=args_.iou_threshold)
