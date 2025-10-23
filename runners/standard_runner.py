# runners/standard_runner.py
from .base_runner import BaseRunner
from core.dfmm import find_factors_for_sum
from utils.helpers import generate_config_hash
import json
import os

class StandardRunner(BaseRunner):
    """
    'auto' または 'manual' モードという、基本的な単一の最適化実行を担当するクラス。
    """
    def run(self):
        # configからターゲット設定を取得
        targets_config_base = self.config.get_targets_config()

        # モードに応じてコンソールにメッセージを表示
        mode_name = "Using manually specified factors..." if self.config.MODE == 'manual' else "Calculating factors automatically..."
        print(mode_name)

        # 'auto' モードの場合、各ターゲットの混合階層（factors）を自動で計算
        if self.config.MODE == 'auto':
            for target in targets_config_base:
                # DFMMアルゴリズムを使って、比率の合計値から因数を探す
                factors = find_factors_for_sum(sum(target['ratios']), self.config.MAX_MIXER_SIZE)
                if factors is None:
                    # 因数が見つからない場合はエラー
                    raise ValueError(f"Could not determine factors for {target['name']}.")
                target['factors'] = factors

        # 'manual' モードの場合は、config.pyで指定された'factors'をそのまま使用する

        # 実行設定から一意のハッシュを生成し、出力ディレクトリ名を決定
        config_hash = generate_config_hash(targets_config_base, self.config.OPTIMIZATION_MODE, self.config.RUN_NAME)
        output_dir = self._get_unique_output_directory_name(config_hash, self.config.RUN_NAME)

        # 準備が整った設定を使って、共通の単一最適化実行メソッドを呼び出す
        self._run_single_optimization(targets_config_base, output_dir, self.config.RUN_NAME)