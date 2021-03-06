from lib.perfBaseTest import PerfBaseTest


class TestSikuli(PerfBaseTest):

    def setUp(self):
        super(TestSikuli, self).setUp()
        self.set_configs(self.config_name.INDEX,
                         self.extract_platform_dep_settings(
                             {'win32': {'7': {'search-margin': 2, 'compare-threshold': 0.015},
                                        '10': {'search-margin': 2, 'compare-threshold': 0.015}}}))

    def test_firefox_gsearch_ail_type_searchbox(self):
        self.test_url = self.global_config['gsearch']['gsearch-home-english']
        self.round_status = self.sikuli.run_test(self.env.test_name, self.env.output_name,
                                                 test_target=self.test_url,
                                                 script_dp=self.env.test_script_py_dp,
                                                 args_list=[self.env.img_sample_dp, self.env.img_output_sample_1_fn,
                                                            self.env.DEFAULT_VIDEO_RECORDING_WIDTH,
                                                            self.env.DEFAULT_VIDEO_RECORDING_HEIGHT,
                                                            self.env.DEFAULT_TIMESTAMP])
