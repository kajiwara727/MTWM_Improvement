# runners/permutation_runner.py
import os
import itertools
import copy
from .base_runner import BaseRunner
from core.dfmm import find_factors_for_sum, generate_unique_permutations
from utils.helpers import generate_config_hash

class PermutationRunner(BaseRunner):
    """
    'auto_permutations' モードの実行を担当するクラス。
    このモードでは、各ターゲットの混合階層（factors）の全てのユニークな順列の
    組み合わせをテストし、どの階層構造が最も良い結果（例：最小廃棄物）を
    生み出すかを網羅的に探索します。
    """
    def run(self):
        # 設定からベースとなるターゲット情報を取得
        targets_config_base = self.config.get_targets_config()
        print("Preparing to test all factor permutations...")

        # 全ての順列実行の結果をまとめるための基本ディレクトリ名を設定
        base_run_name = f"{self.config.RUN_NAME}_permutations"
        config_hash = generate_config_hash(targets_config_base, self.config.OPTIMIZATION_MODE, base_run_name)
        base_output_dir = self._get_unique_output_directory_name(config_hash, base_run_name)
        os.makedirs(base_output_dir, exist_ok=True)
        print(f"All permutation results will be saved under: '{base_output_dir}/'")

        # 各ターゲットに対して、考えられる順列のリストを作成
        target_perms_options = []
        for target in targets_config_base:
            # まず、比率の合計値から基本となる因数分解（factors）を計算
            base_factors = find_factors_for_sum(sum(target['ratios']), self.config.MAX_MIXER_SIZE)
            if base_factors is None:
                raise ValueError(f"Could not determine factors for {target['name']}.")
            # その因数リストからユニークな順列をすべて生成
            perms = generate_unique_permutations(base_factors)
            target_perms_options.append(perms)

        # 全てのターゲットの順列リストから、直積（デカルト積）を計算し、
        # テストすべき全組み合わせを生成
        all_config_combinations = list(itertools.product(*target_perms_options))
        total_runs = len(all_config_combinations)
        print(f"Found {total_runs} unique factor permutation combinations to test.")

        # 生成された各組み合わせについて、最適化を実行
        for i, combo in enumerate(all_config_combinations):
            print(f"\n{'='*20} Running Combination {i+1}/{total_runs} {'='*20}")
            # ベース設定をディープコピーして、現在の組み合わせで上書き
            temp_config = copy.deepcopy(targets_config_base)
            perm_name_parts = []
            for j, target in enumerate(temp_config):
                current_factors = list(combo[j])
                target['factors'] = current_factors
                # 出力ディレクトリ名のために、順列を文字列に変換
                perm_name_parts.append("_".join(map(str, current_factors)))

            # この組み合わせの実行名と出力ディレクトリを決定
            perm_name = "-".join(perm_name_parts)
            run_name = f"run_{i+1}_{perm_name}"
            output_dir = os.path.join(base_output_dir, run_name)

            # 共通の単一最適化実行メソッドを呼び出し
            self._run_single_optimization(temp_config, output_dir, run_name)