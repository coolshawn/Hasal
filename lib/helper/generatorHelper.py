import os
import copy
import time
import json
import shutil
import tempfile
import importlib
import numpy as np
from lib.common.environment import Environment
from lib.common.videoFluency import VideoFluency
from lib.common.commonUtil import CommonUtil
from lib.common.outlier import outlier
from lib.common.dumpDataToJsonFile import dump_data_to_json_file
from lib.common.logConfig import get_logger

logger = get_logger(__name__)
RET_SUCCESSS = 0

DEFAULT_FPS_VALIDATOR_NAME = 'FPSValidator'
DEFAULT_FILEEXIST_VALIDATOR_NAME = 'FileExistValidator'
DEFAULT_DCTRUNTIME_GENERATOR_NAME = 'DctRunTimeGenerator'
DEFAULT_FFMPEG_CONVERTER_NAME = 'FfmpegConverter'
DEFAULT_CV2_CONVERTER_NAME = 'Cv2Converter'
DEFAULT_SAMPLE_CONVERTER_NAME = 'SampleConverter'

DEFAULT_VALIDATOR_SETTINGS = {'modules': {DEFAULT_FPS_VALIDATOR_NAME: {'path': 'lib.validator.fpsValidator'},
                                          DEFAULT_FILEEXIST_VALIDATOR_NAME: {'path': 'lib.validator.fileExistValidator'}}}

DEFAULT_CONVERTER_SETTINGS = {'modules': {DEFAULT_CV2_CONVERTER_NAME: {'path': 'lib.converter.cv2Converter'}}}

DEFAULT_SAMPLE_CONVERTER_SETTINGS = {'modules': {DEFAULT_SAMPLE_CONVERTER_NAME: {'path': 'lib.converter.sampleConverter'}}}

DEFAULT_GENERATOR_SETTINGS = {'modules': {DEFAULT_DCTRUNTIME_GENERATOR_NAME: {'path': 'lib.generator.dctRunTimeGenerator'}}}


def validate_data(validator_settings, validator_data):
    """

    @param validator_settings: use validator name as key to define validator module and module path in dict type
    @param validator_data: use validator name as key to define validator data in dict type
    @return: validate_result , and validator name as key, include with validate result and output_result
    """
    validator_result = {'validate_result': False}
    for validator_name in validator_settings['modules'].keys():
        validator_class = getattr(importlib.import_module(validator_settings['modules'][validator_name]['path']),
                                  validator_name)
        validator_obj = validator_class()
        validate_result = validator_obj.validate(validator_data[validator_name])
        if not validate_result:
            logger.warning(
                "Validator[%s] validate data failed, output is [%s]." % (validator_name, validator_obj.get_output()))
            return validator_result
        else:
            validator_result[validator_name] = {'validate_result': validate_result,
                                                'output_result': validator_obj.get_output()}
    validator_result['validate_result'] = True

    # dump validate result to status file
    dump_data_to_json_file(validator_settings['status_file'], validator_result)
    return validator_result


def run_modules(module_settings, module_data):
    """

    @param module_settings:
    @param module_data:
    @return:
    """
    module_result = {}
    for module_name in module_settings['modules'].keys():
        module_class = getattr(importlib.import_module(module_settings['modules'][module_name]['path']), module_name)
        module_obj = module_class()
        start_time = time.time()
        module_result[module_name] = module_obj.generate_result(module_data)
        last_end = time.time()
        elapsed_time = last_end - start_time
        logger.debug("Module [%s] Time Elapsed: [%s]" % (module_name, elapsed_time))
    return module_result


def run_generators(generator_settings, generator_data):
    """

    @param generator_settings:
    @param generator_data:
    @return:
    """
    generator_result = {}
    for generator_name in generator_settings.keys():
        generator_class = getattr(importlib.import_module(generator_settings[generator_name]['path']), generator_name)
        module_obj = generator_class()
        start_time = time.time()
        generator_result[generator_name] = module_obj.generate_result(generator_data, generator_result)
        last_end = time.time()
        elapsed_time = last_end - start_time
        logger.debug("Generator [%s] Time Elapsed: [%s]" % (generator_name, elapsed_time))
    return generator_result


def output_waveform_info(result_data, waveform_fp, img_dp, video_fp):
    waveform_info = dict()
    waveform_info['video'] = video_fp
    current_run_result = result_data['running_time_result']
    if len(current_run_result) == 2:
        video_fluency_obj = VideoFluency()
        img_list = os.listdir(img_dp)
        img_list.sort(key=CommonUtil.natural_keys)
        start_fn = os.path.basename(current_run_result[0]['image_fp'])
        start_index = img_list.index(start_fn)
        end_fn = os.path.basename(current_run_result[1]['image_fp'])
        end_index = img_list.index(end_fn)
        for img_index in range(len(img_list)):
            img_list[img_index] = os.path.join(img_dp, img_list[img_index])
            if img_index < start_index or img_index > end_index:
                os.remove(img_list[img_index])
        waveform_info['data'], waveform_info['img_list'] = video_fluency_obj.frame_difference(img_dp)
        with open(waveform_fp, "wb") as fh:
            json.dump(waveform_info, fh, indent=2)


def output_video(result_data, video_fp):
    start_fp = None
    end_fp = None
    current_run_result = result_data['running_time_result']
    for event_data in current_run_result:
        if 'start' in event_data:
            start_fp = event_data['start']
        if 'end' in event_data:
            end_fp = event_data['end']
    if not start_fp and not end_fp:
        return None
    else:
        source_dp = os.path.join(os.path.dirname(start_fp), Environment.SEARCH_TARGET_BROWSER)
        img_list = os.listdir(source_dp)
        img_list.sort(key=CommonUtil.natural_keys)
        start_fn = os.path.basename(start_fp)
        end_fn = os.path.basename(end_fp)
        file_ext = os.path.splitext(start_fn)[1]
        extended_range = Environment.DEFAULT_VIDEO_RECORDING_FPS
        start_index = max(0, img_list.index(start_fn) - extended_range)
        end_index = min(len(img_list) - 1, img_list.index(end_fn) + extended_range)
        tempdir = tempfile.mkdtemp()
        count = 0
        for img_index in range(start_index, end_index + 1):
            imf_fp = os.path.join(source_dp, img_list[img_index])
            new_img_fp = os.path.join(tempdir, '{0:05d}'.format(count) + file_ext)
            shutil.copyfile(imf_fp, new_img_fp)
            count += 1

    codec = "ffmpeg"
    source = " -i " + os.path.join(tempdir, "%05d" + file_ext)
    fps = " -r " + str(Environment.DEFAULT_VIDEO_RECORDING_FPS)
    video_format = " -pix_fmt yuv420p"
    video_out = " " + video_fp
    command = codec + source + fps + video_format + video_out
    os.system(command)
    shutil.rmtree(tempdir)


def output_result(test_method_name, result_data, output_fp, time_list_counter_fp, test_method_doc, outlier_check_point, video_fp, web_app_name, revision, pkg_platform, test_output):
    # result = {'class_name': {'total_run_no': 0, 'error_no': 0, 'total_time': 0, 'avg_time': 0, 'max_time': 0, 'min_time': 0, 'time_list':[] 'detail': []}}
    if os.path.exists(output_fp):
        with open(output_fp) as fh:
            result = json.load(fh)
    else:
        result = {}

    current_run_result = result_data['running_time_result']

    start_time = 0
    end_time = 0
    for event_data in current_run_result:
        if 'start' in event_data:
            start_time = event_data['time_seq']
        if 'end' in event_data:
            end_time = event_data['time_seq']
    run_time = end_time - start_time

    event_time_dict = dict()
    for event_data in current_run_result:
        for event_name in event_data:
            if event_name != 'time_seq' and event_name != 'start' and event_name != 'end':
                event_time_dict[event_name] = np.absolute(event_data['time_seq'] - start_time)

    calc_obj = outlier()
    if "speed_index" in result_data:
        si_value = result_data['speed_index']
        psi_value = result_data['perceptual_speed_index']
    else:
        si_value = 0
        psi_value = 0
    run_time_dict = {'run_time': run_time, 'si': si_value, 'psi': psi_value, 'folder': test_output}
    run_time_dict.update(event_time_dict)

    if test_method_name in result:
        result[test_method_name]['total_run_no'] += 1
        result[test_method_name]['total_time'] += run_time
        if run_time == 0:
            result[test_method_name]['error_no'] += 1
        else:
            result[test_method_name]['time_list'].append(run_time_dict)
        if run_time > result[test_method_name]['max_time']:
            result[test_method_name]['max_time'] = run_time
        if run_time < result[test_method_name]['min_time']:
            result[test_method_name]['min_time'] = run_time
        result[test_method_name]['detail'].extend(current_run_result)
        if len(result[test_method_name]['time_list']) >= outlier_check_point:
            result[test_method_name]['avg_time'], result[test_method_name]['med_time'],\
                result[test_method_name]['std_dev'], result[test_method_name]['time_list'],\
                tmp_outlier, si_value, psi_value = calc_obj.detect(result[test_method_name]['time_list'])
            result[test_method_name]['outlier'].extend(tmp_outlier)
            result[test_method_name]['min_time'] = result[test_method_name]['time_list'][0]['run_time']
            result[test_method_name]['max_time'] = result[test_method_name]['time_list'][-1]['run_time']
    else:
        result[test_method_name] = {}
        result[test_method_name]['description'] = test_method_doc
        result[test_method_name]['total_run_no'] = 1
        result[test_method_name]['total_time'] = run_time
        result[test_method_name]['time_list'] = []
        result[test_method_name]['outlier'] = []
        if run_time == 0:
            result[test_method_name]['error_no'] = 1
            result[test_method_name]['max_time'] = 0
            result[test_method_name]['min_time'] = 0
        else:
            result[test_method_name]['error_no'] = 0
            result[test_method_name]['avg_time'] = run_time
            result[test_method_name]['med_time'] = run_time
            result[test_method_name]['max_time'] = run_time
            result[test_method_name]['min_time'] = run_time
            result[test_method_name]['time_list'].append(run_time_dict)
        result[test_method_name]['detail'] = current_run_result

    result[test_method_name]['video_fp'] = video_fp
    result[test_method_name]['web_app_name'] = web_app_name
    result[test_method_name]['speed_index'] = si_value
    result[test_method_name]['perceptual_speed_index'] = psi_value
    result[test_method_name]['revision'] = revision
    result[test_method_name]['pkg_platform'] = pkg_platform

    with open(output_fp, "wb") as fh:
        json.dump(result, fh, indent=2)

    # output sikuli status to static file
    with open(time_list_counter_fp, "r+") as fh:
        stat_data = json.load(fh)
        stat_data['time_list_counter'] = str(len(result[test_method_name]['time_list']))
        fh.seek(0)
        fh.write(json.dumps(stat_data))


def calculate(env, exec_timestamp_list, crop_data=None, calc_si=0, waveform=0, revision="", pkg_platform="", suite_upload_dp=""):
    """

    @param env: from lib.common.environment.py
    @param exec_timestamp_list: timestamp list
    @param crop_data: sample crop data area
    @param calc_si: '1' or '0'
    @param waveform: '1' or '0'
    @param revision:  upload to perfherder revision
    @param pkg_platform:  upload to perfherder pkg platform name
    @param suite_upload_dp: folder consolidate all execution result
    @return:
    """
    calculator_result = None

    # validation data assign
    validator_data = {DEFAULT_FPS_VALIDATOR_NAME: {'recording_log_fp': env.recording_log_fp, 'default_fps': env.DEFAULT_VIDEO_RECORDING_FPS},
                      DEFAULT_FILEEXIST_VALIDATOR_NAME: {'check_fp_list': [env.video_output_fp]}}
    validator_settings = copy.deepcopy(DEFAULT_VALIDATOR_SETTINGS)
    validator_settings['status_file'] = env.DEFAULT_STAT_RESULT

    # will do the analyze after validate pass
    validate_result = validate_data(validator_settings, validator_data)

    if validate_result['validate_result']:
        # using different converter will introduce different time seq,
        # the difference range will betweeen 0.000000000002 to 0.000000000004 ms (cv2 is lower than ffmpeg)
        converter_settings = copy.deepcopy(DEFAULT_CONVERTER_SETTINGS)
        converter_data = {
            DEFAULT_CV2_CONVERTER_NAME: {'video_fp': env.video_output_fp, 'output_img_dp': env.img_output_dp,
                                         'convert_fmt': 'bmp',
                                         'current_fps': validate_result[DEFAULT_FPS_VALIDATOR_NAME]['output_result'],
                                         'exec_timestamp_list': exec_timestamp_list}}
        converter_result = run_modules(converter_settings, converter_data[DEFAULT_CV2_CONVERTER_NAME])

        sample_settings = copy.deepcopy(DEFAULT_SAMPLE_CONVERTER_SETTINGS)
        sample_data = {'sample_dp': env.img_sample_dp,
                       'configuration': {'generator': {DEFAULT_DCTRUNTIME_GENERATOR_NAME: {'path': 'lib.generator.dctRunTimeGenerator'}},
                                         'crop_data': {2: {"range": [(70, 65), (920, 100)]}}}}

        # {1:{'fp': 'xxcxxxx', 'DctRunTimeGenerator': 'dctobj', 'SSIMRunTimeGenerator': None, },
        #  2:{'fp':'xxxxx', 'SSIMRunTimeGenerator': None, 'crop_fp': 'xxxxxxx', 'viewport':'xxxxx'},
        #  }

        sample_result = run_modules(sample_settings, sample_data)

        generator_settings = sample_data['configuration']['generator']
        generator_data = {'converter_result': converter_result[DEFAULT_CV2_CONVERTER_NAME], 'sample_result': sample_result[DEFAULT_SAMPLE_CONVERTER_NAME],
                          'default_fps': env.DEFAULT_VIDEO_RECORDING_FPS, 'exec_timestamp_list': exec_timestamp_list}
        generator_result = run_generators(generator_settings, generator_data)

        # To support legacy function output result need to put all result in running time result key
        for generator_name in sample_data['configuration']['generator']:
            if generator_result[generator_name]:
                if calculator_result:
                    calculator_result['running_time_result'].update(generator_result[generator_name])
                else:
                    calculator_result = {'running_time_result': generator_result[generator_name]}

        # output sikuli status to static file
        with open(env.DEFAULT_STAT_RESULT, "r+") as fh:
            stat_data = json.load(fh)
            stat_data['fps_stat'] = validate_result[DEFAULT_FPS_VALIDATOR_NAME]['output_result']
            fh.seek(0)
            fh.write(json.dumps(stat_data))

        if calculator_result is not None:
            output_result(env.test_name, calculator_result, env.DEFAULT_TEST_RESULT, env.DEFAULT_STAT_RESULT,
                          env.test_method_doc, env.DEFAULT_OUTLIER_CHECK_POINT, env.video_output_fp,
                          env.web_app_name, revision, pkg_platform, env.output_name)
            start_time = time.time()
            output_video(calculator_result, env.converted_video_output_fp)
            current_time = time.time()
            elapsed_time = current_time - start_time
            logger.debug("Generate Video Elapsed: [%s]" % elapsed_time)
            if waveform == 1:
                output_waveform_info(calculator_result, env.waveform_fp, env.img_output_dp, env.video_output_fp)

            upload_case_name = "_".join(env.output_name.split("_")[2:-1])
            upload_case_dp = os.path.join(suite_upload_dp, upload_case_name)
            if os.path.exists(upload_case_dp) is False:
                os.mkdir(upload_case_dp)
            shutil.move(env.converted_video_output_fp, upload_case_dp)