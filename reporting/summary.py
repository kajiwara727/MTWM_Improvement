# reporting/summary.py (修正版)
import os

def _calculate_and_save_summary(results_list, output_dir, filename_prefix, title_prefix, objective_mode):
    """
    共通の計算ロジックを使用して、サマリーファイルを作成し、平均値を追加する。
    """
    # サマリーファイルのフルパスを構築
    filepath = os.path.join(output_dir, f"_{filename_prefix}_summary.txt")

    # ファイルのヘッダー部分を作成
    content = [
        "==================================================",
        f"      Summary of All {title_prefix} Simulation Runs       ",
        "==================================================",
        f"\nTotal simulations executed: {len(results_list)}\n"
    ]

    # 各実行結果をループして、コンテンツに追加
    for result in results_list:
        content.append("-" * 50)
        content.append(f"Run Name: {result['run_name']}")
        content.append(f"  -> Execution Time: {result['elapsed_time']:.2f} seconds")

        if result['final_value'] is not None:
            # Objective Modeに応じてラベルを変更
            mode_lower = objective_mode.lower()
            objective_label = "Final Objective Value"
            if mode_lower == 'waste':
                 objective_label = "Minimum Waste Found"
            elif mode_lower == 'operations':
                 objective_label = "Minimum Operations Found"
            elif mode_lower == 'reagents':
                 objective_label = "Minimum Reagents Found"
            
            content.append(f"  -> {objective_label}: {result['final_value']}")
            
            # その他の結果はそのまま追加
            content.append(f"  -> Total Operations: {result.get('total_operations', 'N/A')}")
            content.append(f"  -> Total Reagent Units: {result.get('total_reagents', 'N/A')}")
            # Total waste は objective_mode が waste でない場合も出力
            total_waste = result.get('total_waste', 'N/A')
            if total_waste != 'N/A':
                 content.append(f"  -> Total Waste Generated: {total_waste}")
        else:
            # 解が見つからなかった場合
            content.append("  -> No solution was found for this configuration.")

        # その実行で使用されたターゲット設定を記録 (比較実行ではconfigキーが存在しない場合があるためスキップ)
        if 'config' in result and result['config']:
            content.append("  -> Target Configurations:")
            for i, config in enumerate(result['config']):
                ratios_str = ', '.join(map(str, config['ratios']))
                content.append(f"    - Target {i+1}: Ratios = [{ratios_str}]")
            content.append("")
            
    # --- 平均値の計算と追加ロジック ---
    successful_runs = [r for r in results_list if r['final_value'] is not None]
    num_successful_runs = len(successful_runs)
    mode_label = objective_mode.title()

    if num_successful_runs > 0:
        # final_valueが何を表しているかに応じて、その平均も計算
        total_final_value = sum(r['final_value'] for r in successful_runs)
        
        # NOTE: file_load_runner.pyの修正により、total_wasteはwasteモードでない場合もNoneとして格納される
        total_waste = sum(r.get('total_waste', 0) for r in successful_runs if r.get('total_waste') is not None)
        total_operations = sum(r.get('total_operations', 0) for r in successful_runs)
        total_reagents = sum(r.get('total_reagents', 0) for r in successful_runs)

        avg_final_value = total_final_value / num_successful_runs
        avg_waste = total_waste / num_successful_runs
        avg_operations = total_operations / num_successful_runs
        avg_reagents = total_reagents / num_successful_runs

        # 結果をサマリーに追加
        content.append("\n" + "="*50)
        content.append(f"        Average Results (based on {num_successful_runs} successful runs)        ")
        content.append("="*50)
        content.append(f"Average Objective Value ({mode_label}): {avg_final_value:.2f}")
        content.append(f"Average Total Waste: {avg_waste:.2f}")
        content.append(f"Average Total Operations: {avg_operations:.2f}")
        content.append(f"Average Total Reagent Units: {avg_reagents:.2f}")
        content.append("="*50)
    else:
        content.append("\nNo successful runs found to calculate averages.")
    # --- END FIX ---


    try:
        # 構築したコンテンツをファイルに書き込み
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        # 成功メッセージをコンソールに出力
        print("\n" + "="*60)
        print(f"SUCCESS: A summary of all {title_prefix} runs has been saved to:")
        print(f"  -> {filepath}")
        print("="*60)
        return True
    except IOError as e:
        # エラーハンドリング
        print(f"\nError saving {title_prefix} run summary file: {e}")
        return False


def save_random_run_summary(results_list, output_dir):
    """
    'random' モードで実行された全シミュレーションの結果概要を、
    単一のサマリーファイルに保存します。
    """
    # random_runnerは常に waste mode とは限らないため、objective_modeをresults_listに追加する
    updated_results = []
    for r in results_list:
        if 'objective_mode' not in r: # random_runnerにはobjective_modeがないため、ここでは仮に'Waste'とする
            r['objective_mode'] = 'Waste' 
        updated_results.append(r)
    _calculate_and_save_summary(updated_results, output_dir, "random_runs", "Random", "Waste")
    
    

def save_comparison_summary(results_list, output_dir, objective_mode):
    """
    'file_load' モードで実行された比較シミュレーションの結果概要を、
    単一のサマリーファイルに保存します。
    """
    _calculate_and_save_summary(results_list, output_dir, "comparison_runs", "Comparison", objective_mode)