# runners/file_load_runner.py (Final version with collection and summary)

from .base_runner import BaseRunner
from utils.helpers import generate_config_hash
from reporting.summary import save_comparison_summary # <--- 変更
import json
import os

class FileLoadRunner(BaseRunner):
    """
    設定ファイル (config.CONFIG_LOAD_FILE) からターゲット設定を読み込み、
    最適化を実行する専用のRunner。
    """
    def run(self):
        targets_configs_to_run = []
        
        config_path = self.config.CONFIG_LOAD_FILE

        if not config_path:
            raise ValueError("CONFIG_LOAD_FILEが設定されていません。config.pyにファイルパスを指定してください。")

        # --- 設定ファイルからの読み込みロジック ---
        try:
            print(f"Loading configuration from file: {config_path}...")
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            if not data:
                raise ValueError("設定ファイルが空です。")
            
            if isinstance(data, list) and len(data) > 0:
                # Case 1: Multiple runs saved by random_runner (e.g., [{'run_name':..., 'targets': [...]}, ...])
                if 'targets' in data[0]:
                    targets_configs_to_run = data
                # Case 2: A simple list of targets (e.g., [{'name':..., 'ratios':..., 'factors':...}, ...])
                elif 'ratios' in data[0]:
                    targets_configs_to_run.append({'run_name': self.config.RUN_NAME, 'targets': data})
                else:
                    raise ValueError("設定ファイルの構造が無効です。ターゲットのリスト、またはランオブジェクトのリストが必要です。")
            
        except FileNotFoundError:
            raise FileNotFoundError(f"設定ファイルが見つかりません: {config_path}")
        except json.JSONDecodeError:
            raise ValueError(f"JSONデコードエラー: {config_path}。ファイルが正しいJSON形式であることを確認してください。")
        except Exception as e:
            raise RuntimeError(f"設定の読み込み中にエラーが発生しました: {e}")

        if not targets_configs_to_run:
             raise ValueError("設定ファイルからターゲットが読み込まれませんでした。")

        print(f"Configuration successfully loaded. Found {len(targets_configs_to_run)} pattern(s) to run.")

        all_comparison_results = [] # <--- 結果を収集するためのリスト

        # 全実行結果をまとめるためのルートディレクトリを作成
        base_output_dir = self._get_unique_output_directory_name(self.config.RUN_NAME, self.config.RUN_NAME + "_comparison")
        os.makedirs(base_output_dir, exist_ok=True)
        print(f"All comparison results will be saved under: '{base_output_dir}/'")

        for i, run_data in enumerate(targets_configs_to_run):
            run_name_prefix = run_data.get('run_name', f"Run_{i+1}")
            targets_config_base = run_data['targets']
            
            print(f"\n{'='*20} Running Loaded Pattern {i+1}/{len(targets_configs_to_run)} ({run_name_prefix}) {'='*20}")

            # 実行名を設定し、ハッシュを生成
            base_run_name = run_name_prefix + f"_loaded"
            
            config_hash = generate_config_hash(targets_config_base, self.config.OPTIMIZATION_MODE, base_run_name)
            
            # 個々の実行結果をルートディレクトリ内のユニークなフォルダに保存
            output_dir_name = self._get_unique_output_directory_name(config_hash, base_run_name)
            output_dir = os.path.join(base_output_dir, output_dir_name)

            # 共通の単一最適化実行メソッドを呼び出す
            final_value, exec_time, total_ops, total_reagents = self._run_single_optimization(targets_config_base, output_dir, self.config.RUN_NAME)
            
            # --- 結果の収集 ---
            # total_wasteを明示的に格納
            total_waste = final_value if self.config.OPTIMIZATION_MODE.lower() == 'waste' else total_ops if self.config.OPTIMIZATION_MODE.lower() == 'operations' else total_reagents
            
            # wasteモードでなければ、final_value (目的値) と total_waste (計算されたwaste) は異なるため、総waste量を別途計算する
            if self.config.OPTIMIZATION_MODE.lower() != 'waste':
                # total_wasteを別途取得するため、analyze_solutionを実行したreporterを再利用する必要があるが、
                # _run_single_optimizationの外部からはアクセスできないため、暫定的にNoneとする。
                # ただし、現状の_run_single_optimizationの返り値から total_ops, total_reagents は取得できているため、
                # total_wasteは総waste量の最小値が目的値でない限り、正確な値を求めることができない。
                # ここでは、簡便のために total_waste の値を final_value と区別して格納する。
                pass # final_value, total_ops, total_reagents はそのまま使用
            
            all_comparison_results.append({
                'run_name': run_name_prefix, 
                'final_value': final_value, 
                'elapsed_time': exec_time,
                'total_operations': total_ops, 
                'total_reagents': total_reagents,
                'total_waste': total_waste if self.config.OPTIMIZATION_MODE.lower() == 'waste' else None, # wasteが目的値の場合のみ格納
                'config': targets_config_base,
                'objective_mode': self.config.OPTIMIZATION_MODE
            })
            # --- 収集終わり ---

        # --- 全比較実行結果のサマリー保存 ---
        save_comparison_summary(all_comparison_results, base_output_dir, self.config.OPTIMIZATION_MODE)
        
        print("\nAll comparison runs finished successfully.")