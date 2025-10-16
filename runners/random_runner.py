# runners/random_runner.py
import os
from .base_runner import BaseRunner
from core.dfmm import find_factors_for_sum
from utils.helpers import generate_random_ratios
from reporting.summary import save_random_run_summary

class RandomRunner(BaseRunner):
    """
    'random' モードの実行を担当するクラス。
    このモードでは、config.pyのRANDOM_SETTINGSで定義されたパラメータに基づき、
    ランダムな比率を持つターゲットを複数生成し、それぞれのシナリオで
    最適化を実行します。統計的な分析や、様々な条件下でのソルバーの
    性能評価に役立ちます。
    """
    def run(self):
        # 'random' モード用の設定を取得
        settings = self.config.RANDOM_SETTINGS
        print(f"Preparing to run {settings['k_runs']} random simulations...")

        # 全てのランダム実行の結果をまとめるための基本ディレクトリ名を設定
        base_run_name = f"{self.config.RUN_NAME}_random_runs"
        # ランダム実行は設定が都度変わるため、ハッシュは固定文字列 "random" を使用
        base_output_dir = self._get_unique_output_directory_name("random", base_run_name)
        os.makedirs(base_output_dir, exist_ok=True)
        print(f"All random run results will be saved under: '{base_output_dir}/'")

        all_run_results = [] # 全実行結果をサマリー用に保存するリスト

        # 設定された回数 (k_runs) だけループを実行
        for i in range(settings['k_runs']):
            print(f"\n{'='*20} Running Random Simulation {i+1}/{settings['k_runs']} {'='*20}")

            # このシミュレーションで使用するターゲット設定を動的に生成
            temp_config = []
            for j in range(settings['n_targets']):
                # 指定された試薬数と合計値になるランダムな比率リストを生成
                ratios = generate_random_ratios(settings['t_reagents'], settings['S_ratio_sum'])
                # 生成された比率から、混合階層 (factors) を自動計算
                factors = find_factors_for_sum(sum(ratios), self.config.MAX_MIXER_SIZE)
                if factors is None:
                    # 階層を決定できない場合は、この実行をスキップ
                    print(f"Warning: Could not determine factors for random ratios {ratios}. Skipping this run.")
                    continue
                temp_config.append({
                    'name': f"RandomTarget_{i+1}_{j+1}",
                    'ratios': ratios,
                    'factors': factors
                })

            if not temp_config: continue # 有効なターゲットが生成されなかった場合

            # この実行の名称と出力ディレクトリを設定
            run_name = f"run_{i+1}"
            output_dir = os.path.join(base_output_dir, run_name)

            # 共通の単一最適化実行メソッドを呼び出し
            final_waste, exec_time, total_ops, total_reagents = self._run_single_optimization(temp_config, output_dir, run_name)

            # 結果をサマリー用リストに追加
            all_run_results.append({
                'run_name': run_name, 'config': temp_config,
                'final_value': final_waste, 'elapsed_time': exec_time,
                'total_operations': total_ops, 'total_reagents': total_reagents
            })

        # 全ての実行が完了したら、サマリーレポートを生成・保存
        save_random_run_summary(all_run_results, base_output_dir)