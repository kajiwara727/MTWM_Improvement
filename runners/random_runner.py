import os
import random
import json
from .base_runner import BaseRunner
from core.dfmm import find_factors_for_sum
from utils.helpers import generate_random_ratios
from reporting.summary import save_random_run_summary

class RandomRunner(BaseRunner):
    """
    'random' モードの実行を担当するクラス。
    config.py の RANDOM_... 変数に基づき、ランダムなシナリオを複数回実行します。
    """

    def run(self):
        num_runs = self.config.RANDOM_K_RUNS
        num_targets = self.config.RANDOM_N_TARGETS
        num_reagents = self.config.RANDOM_T_REAGENTS
        sequence = self.config.RANDOM_S_RATIO_SUM_SEQUENCE
        candidates = self.config.RANDOM_S_RATIO_SUM_CANDIDATES
        default_sum = self.config.RANDOM_S_RATIO_SUM_DEFAULT

        print(f"Preparing to run {num_runs} random simulations...")

        base_run_name = f"{self.config.RUN_NAME}_random_runs"
        base_output_dir = self._get_unique_output_directory_name(
            "random", base_run_name
        )
        os.makedirs(base_output_dir, exist_ok=True)
        print(f"All random run results will be saved under: '{base_output_dir}/'")

        all_run_results = []
        saved_configs = []

        for run_idx in range(num_runs):
            print(
                f"\n{'='*20} Running Random Simulation {run_idx+1}/{num_runs} {'='*20}"
            )

            specs_for_run = []
            if sequence and isinstance(sequence, list) and len(sequence) == num_targets:
                specs_for_run = sequence
                print(
                    f"-> Mode: Fixed Sequence. Using S_ratio_sum specifications: {specs_for_run}"
                )
            elif candidates and isinstance(candidates, list) and len(candidates) > 0:
                specs_for_run = [random.choice(candidates) for _ in range(num_targets)]
                print(
                    f"-> Mode: Random per Target. Generated S_ratio_sum specifications for this run: {specs_for_run}"
                )
            else:
                specs_for_run = [default_sum] * num_targets
                print(
                    f"-> Mode: Default. Using single S_ratio_sum '{default_sum}' for all targets."
                )

            current_run_config = []
            valid_run = True
            for target_idx in range(num_targets):
                spec = specs_for_run[target_idx]
                base_sum = 0
                multiplier = 1
                if isinstance(spec, dict):
                    base_sum = spec.get("base_sum", 0)
                    multiplier = spec.get("multiplier", 1)
                elif isinstance(spec, (int, float)):
                    base_sum = int(spec)
                    multiplier = 1
                else:
                    print(
                        f"Warning: Invalid spec format for target {target_idx+1}: {spec}. Skipping this run."
                    )
                    valid_run = False
                    break
                if base_sum <= 0:
                    print(
                        f"Warning: Invalid base_sum ({base_sum}) for target {target_idx+1}. Skipping this run."
                    )
                    valid_run = False
                    break
                try:
                    base_ratios = generate_random_ratios(num_reagents, base_sum)
                    ratios = [r * multiplier for r in base_ratios]
                    print(f"  -> Target {target_idx+1}: Spec={spec}")
                    print(
                        f"     Base ratios (sum={base_sum}): {base_ratios} -> Multiplied by {multiplier} -> Final Ratios (sum={sum(ratios)}): {ratios}"
                    )
                except ValueError as e:
                    print(
                        f"Warning: Could not generate base ratios for sum {base_sum}. Error: {e}. Skipping this run."
                    )
                    valid_run = False
                    break

                base_factors = find_factors_for_sum(
                    base_sum, self.config.MAX_MIXER_SIZE
                )
                if base_factors is None:
                    print(
                        f"Warning: Could not determine factors for base_sum {base_sum}. Skipping this run."
                    )
                    valid_run = False
                    break
                multiplier_factors = find_factors_for_sum(
                    multiplier, self.config.MAX_MIXER_SIZE
                )
                if multiplier_factors is None:
                    print(
                        f"Warning: Could not determine factors for multiplier {multiplier}. Skipping this run."
                    )
                    valid_run = False
                    break
                factors = base_factors + multiplier_factors
                factors.sort(reverse=True)
                print(
                    f"     Factors for base ({base_sum}): {base_factors} + Factors for multiplier ({multiplier}): {multiplier_factors} -> Sorted Final Factors: {factors}"
                )

                current_run_config.append(
                    {
                        "name": f"RandomTarget_{run_idx+1}_{target_idx+1}",
                        "ratios": ratios,
                        "factors": factors,
                    }
                )

            if not valid_run or not current_run_config:
                continue

            run_name = f"run_{run_idx+1}"
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
                    "config": current_run_config,
                    "final_value": final_value,
                    "elapsed_time": exec_time,
                    "total_operations": total_ops,
                    "total_reagents": total_reagents,
                    "total_waste": total_waste,
                    "objective_mode": self.config.OPTIMIZATION_MODE,
                }
            )

            saved_configs.append({"run_name": run_name, "targets": current_run_config})

        save_random_run_summary(all_run_results, base_output_dir)
        config_log_path = os.path.join(base_output_dir, "random_configs.json")
        with open(config_log_path, "w", encoding="utf-8") as f:
            json.dump(saved_configs, f, indent=4)
        print(f"\nAll generated configurations saved to: {config_log_path}")
