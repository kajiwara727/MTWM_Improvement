# runners/permutation_runner.py
import os
import itertools
import copy
from .base_runner import BaseRunner
from core.dfmm import find_factors_for_sum, generate_unique_permutations
from utils.helpers import generate_config_hash
from reporting.summary import save_permutation_summary


class PermutationRunner(BaseRunner):
    """
    'auto_permutations' モードの実行を担当するクラス。
    """

    def run(self):
        targets_config_base = self.config.get_targets_config()
        print("Preparing to test all factor permutations...")

        base_run_name = f"{self.config.RUN_NAME}_permutations"
        config_hash = generate_config_hash(
            targets_config_base, self.config.OPTIMIZATION_MODE, base_run_name
        )
        base_output_dir = self._get_unique_output_directory_name(
            config_hash, base_run_name
        )
        os.makedirs(base_output_dir, exist_ok=True)
        print(f"All permutation results will be saved under: '{base_output_dir}/'")

        target_perms_options = []
        for target in targets_config_base:
            base_factors = find_factors_for_sum(
                sum(target["ratios"]), self.config.MAX_MIXER_SIZE
            )
            if base_factors is None:
                raise ValueError(f"Could not determine factors for {target['name']}.")
            perms = generate_unique_permutations(base_factors)
            target_perms_options.append(perms)

        all_config_combinations = list(itertools.product(*target_perms_options))
        total_runs = len(all_config_combinations)
        print(f"Found {total_runs} unique factor permutation combinations to test.")

        all_run_results = []

        for perm_idx, factor_permutation in enumerate(all_config_combinations):
            print(f"\n{'='*20} Running Combination {perm_idx+1}/{total_runs} {'='*20}")

            current_run_config = copy.deepcopy(targets_config_base)
            perm_name_parts = []

            for target_idx, target in enumerate(current_run_config):
                current_factors = list(factor_permutation[target_idx])
                target["factors"] = current_factors
                perm_name_parts.append("_".join(map(str, current_factors)))

            perm_name = "-".join(perm_name_parts)
            run_name = f"run_{perm_idx+1}_{perm_name}"
            output_dir = os.path.join(base_output_dir, run_name)

            (
                final_value,
                exec_time,
                total_ops,
                total_reagents,
                total_waste,
            ) = self._run_single_optimization(current_run_config, output_dir, run_name)

            all_run_results.append(
                {
                    "run_name": run_name,
                    "targets": copy.deepcopy(current_run_config),
                    "final_value": final_value,
                    "elapsed_time": exec_time,
                    "total_operations": total_ops,
                    "total_reagents": total_reagents,
                    "total_waste": total_waste,
                    "objective_mode": self.config.OPTIMIZATION_MODE,
                }
            )

        save_permutation_summary(
            all_run_results, base_output_dir, self.config.OPTIMIZATION_MODE
        )
