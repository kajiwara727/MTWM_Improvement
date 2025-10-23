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
    config.pyのRANDOM_SETTINGSに基づき、ランダムなシナリオを複数回実行します。
    """
    def run(self):
        settings = self.config.RANDOM_SETTINGS
        print(f"Preparing to run {settings['k_runs']} random simulations...")

        base_run_name = f"{self.config.RUN_NAME}_random_runs"
        base_output_dir = self._get_unique_output_directory_name("random", base_run_name)
        os.makedirs(base_output_dir, exist_ok=True)
        print(f"All random run results will be saved under: '{base_output_dir}/'")

        all_run_results = []
        saved_configs = [] # <--- 追加: 生成された設定を保存するリスト

        for i in range(settings['k_runs']):
            print(f"\n{'='*20} Running Random Simulation {i+1}/{settings['k_runs']} {'='*20}")

            # --- 混合比和の決定ロジック ---
            sequence = settings.get('S_ratio_sum_sequence')
            candidates = settings.get('S_ratio_sum_candidates')
            n_targets = settings.get('n_targets', 0)
            
            if sequence and isinstance(sequence, list) and len(sequence) == n_targets:
                mode = 'sequence'
                specs_for_run = sequence
                print(f"-> Mode: Fixed Sequence. Using S_ratio_sum specifications: {specs_for_run}")
            
            elif candidates and isinstance(candidates, list) and len(candidates) > 0:
                mode = 'random_candidates'
                specs_for_run = [random.choice(candidates) for _ in range(n_targets)]
                print(f"-> Mode: Random per Target. Generated S_ratio_sum specifications for this run: {specs_for_run}")

            else:
                mode = 'default'
                default_sum = settings.get('S_ratio_sum', 0)
                specs_for_run = [default_sum] * n_targets
                print(f"-> Mode: Default. Using single S_ratio_sum '{default_sum}' for all targets.")
            
            temp_config = []
            valid_run = True
            for j in range(n_targets):
                spec = specs_for_run[j]
                
                # --- spec（設定値）を解析して、base_sumとmultiplierを決定 ---
                base_sum = 0
                multiplier = 1
                
                if isinstance(spec, dict):
                    base_sum = spec.get('base_sum', 0)
                    multiplier = spec.get('multiplier', 1)
                elif isinstance(spec, (int, float)):
                    base_sum = int(spec)
                    multiplier = 1
                else:
                    print(f"Warning: Invalid spec format for target {j+1}: {spec}. Skipping this run.")
                    valid_run = False
                    break
                
                if base_sum <= 0:
                    print(f"Warning: Invalid base_sum ({base_sum}) for target {j+1}. Skipping this run.")
                    valid_run = False
                    break
                
                try:
                    # 1. 基本比率を生成
                    base_ratios = generate_random_ratios(settings['t_reagents'], base_sum)
                    # 2. 倍率を適用して最終的な比率を計算
                    ratios = [r * multiplier for r in base_ratios]
                    
                    print(f"  -> Target {j+1}: Spec={spec}")
                    print(f"     Base ratios (sum={base_sum}): {base_ratios} -> Multiplied by {multiplier} -> Final Ratios (sum={sum(ratios)}): {ratios}")
                except ValueError as e:
                    print(f"Warning: Could not generate base ratios for sum {base_sum}. Error: {e}. Skipping this run.")
                    valid_run = False
                    break

                # 3. factorsを「base_sumの因数」と「multiplierの因数」の合成で生成
                base_factors = find_factors_for_sum(base_sum, self.config.MAX_MIXER_SIZE)
                if base_factors is None:
                    print(f"Warning: Could not determine factors for base_sum {base_sum}. Skipping this run.")
                    valid_run = False
                    break

                multiplier_factors = find_factors_for_sum(multiplier, self.config.MAX_MIXER_SIZE)
                if multiplier_factors is None:
                    print(f"Warning: Could not determine factors for multiplier {multiplier}. Skipping this run.")
                    valid_run = False
                    break
                
                factors = base_factors + multiplier_factors
                
                # 【変更点】factorsリストを降順（大きい順）にソートします
                factors.sort(reverse=True)
                
                print(f"     Factors for base ({base_sum}): {base_factors} + Factors for multiplier ({multiplier}): {multiplier_factors} -> Sorted Final Factors: {factors}")

                temp_config.append({
                    'name': f"RandomTarget_{i+1}_{j+1}",
                    'ratios': ratios,
                    'factors': factors
                })

            if not valid_run or not temp_config:
                continue

            run_name = f"run_{i+1}"
            output_dir = os.path.join(base_output_dir, run_name)

            final_waste, exec_time, total_ops, total_reagents = self._run_single_optimization(temp_config, output_dir, run_name)

            all_run_results.append({
                'run_name': run_name, 'config': temp_config,
                'final_value': final_waste, 'elapsed_time': exec_time,
                'total_operations': total_ops, 'total_reagents': total_reagents
            })

            saved_configs.append({
                'run_name': run_name,
                'targets': temp_config
            })

        save_random_run_summary(all_run_results, base_output_dir)
        config_log_path = os.path.join(base_output_dir, "random_configs.json")
        with open(config_log_path, 'w', encoding='utf-8') as f:
            json.dump(saved_configs, f, indent=4)
        print(f"\nAll generated configurations saved to: {config_log_path}")