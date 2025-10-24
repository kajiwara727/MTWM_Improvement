# runners/base_runner.py
import os
from abc import ABC, abstractmethod

from core.problem import MTWMProblem
from core.dfmm import build_dfmm_forest, calculate_p_values_from_structure
from or_tools_solver import OrToolsSolver
from reporting.reporter import SolutionReporter
from reporting.analyzer import PreRunAnalyzer
from utils.helpers import generate_config_hash


class BaseRunner(ABC):

    def __init__(self, config):
        self.config = config

    @abstractmethod
    def run(self):
        raise NotImplementedError

    def _get_unique_output_directory_name(self, config_hash, base_name_prefix):
        base_name = f"{base_name_prefix}_{config_hash[:8]}"
        output_dir = base_name
        counter = 1
        while os.path.isdir(output_dir):
            output_dir = f"{base_name}_{counter}"
            counter += 1
        return output_dir

    def _run_single_optimization(
        self, targets_config_for_run, output_dir, run_name_for_report
    ):
        """
        単一のターゲット設定セットに対して、以下の処理を順番に実行する共通メソッドです。
        """
        print("\n--- Configuration for this run ---")
        print(f"Run Name: {run_name_for_report}")
        for target in targets_config_for_run:
            print(
                f"  - {target['name']}: Ratios = {target['ratios']}, Factors = {target['factors']}"
            )

        print(f"Optimization Mode: {self.config.OPTIMIZATION_MODE.upper()}")

        print("-" * 35 + "\n")

        # 1. DFMMアルゴリズムでツリー構造とP値を計算
        tree_structures = build_dfmm_forest(targets_config_for_run)

        p_value_maps = calculate_p_values_from_structure(
            tree_structures, targets_config_for_run
        )

        # 2. 最適化問題オブジェクトを生成
        problem = MTWMProblem(targets_config_for_run, tree_structures, p_value_maps)

        # 3. 出力ディレクトリを作成し、事前分析レポートを生成
        os.makedirs(output_dir, exist_ok=True)
        print(f"All outputs for this run will be saved to: '{output_dir}/'")
        analyzer = PreRunAnalyzer(problem, tree_structures)
        analyzer.generate_report(output_dir)

        # 4. Or-Toolsソルバーを初期化
        solver = OrToolsSolver(problem, objective_mode=self.config.OPTIMIZATION_MODE)

        # 5. 最適化を実行 (OrToolsSolutionModel を受け取る)
        best_model, final_value, best_analysis, elapsed_time = solver.solve()

        # 6. SolutionReporterを初期化
        reporter = SolutionReporter(
            problem, best_model, objective_mode=self.config.OPTIMIZATION_MODE
        )

        ops = None
        reagents = None
        total_waste = None

        # 7. 結果に応じてレポートを生成
        if best_model:
            # `best_analysis` は `solve` から取得済み
            reporter.generate_full_report(final_value, elapsed_time, output_dir)

            # (best_analysis をサマリー用に取得)
            ops = best_analysis.get("total_operations")
            reagents = best_analysis.get("total_reagent_units")
            total_waste = best_analysis.get("total_waste")
        else:
            print("\n--- No solution found for this configuration ---")

        return final_value, elapsed_time, ops, reagents, total_waste
