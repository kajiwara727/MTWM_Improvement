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
            
            # その他の結果は None の可能性を考慮して 'N/A' にフォールバック
            content.append(f"  -> Total Operations: {result.get('total_operations', 'N/A')}")
            content.append(f"  -> Total Reagent Units: {result.get('total_reagents', 'N/A')}")
            content.append(f"  -> Total Waste Generated: {result.get('total_waste', 'N/A')}")
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
        
        # --- 変更: None を 0 として扱うヘルパー関数 ---
        def sum_safe(key):
            return sum(r.get(key, 0) for r in successful_runs if r.get(key) is not None and isinstance(r.get(key), (int, float)))

        total_final_value = sum_safe('final_value')
        total_waste = sum_safe('total_waste')
        total_operations = sum_safe('total_operations')
        total_reagents = sum_safe('total_reagents')
        # --- 変更ここまで ---

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
    【変更】'random' モードで実行された全シミュレーションの結果概要を、
    単一のサマリーファイルに保存します。
    """
    # 目的モードを最初の結果から取得 (全ランで共通のはず)
    objective_mode = 'waste' # デフォルト
    if results_list and 'objective_mode' in results_list[0]:
        objective_mode = results_list[0]['objective_mode']
    
    _calculate_and_save_summary(results_list, output_dir, "random_runs", "Random", objective_mode)
    
    

def save_comparison_summary(results_list, output_dir, objective_mode):
    """
    'file_load' モードで実行された比較シミュレーションの結果概要を、
    単一のサマリーファイルに保存します。
    """
    _calculate_and_save_summary(results_list, output_dir, "comparison_runs", "Comparison", objective_mode)

def save_permutation_summary(results_list, output_dir, objective_mode):
    """
    'auto_permutations' モードの結果を分析し、ベストおよびセカンドベストのパターンを
    詳細なサマリーファイル (_permutation_summary.txt) に保存します。
    """
    # 1. ソートキーを設定 (Noneでない値のみを対象とし、最小値がベスト)
    successful_runs = [r for r in results_list if r['final_value'] is not None]
    
    # final_value (目的値) でソート (昇順)
    successful_runs.sort(key=lambda x: x['final_value'])
    
    if not successful_runs:
        print("\n[Permutation Summary] No successful runs found.")
        return

    min_value = successful_runs[0]['final_value']
    
    # 2. ベストパターン (Min value) を抽出
    best_patterns = [r for r in successful_runs if r['final_value'] == min_value]
    
    # 3. セカンドベストパターン (Second Min value) を抽出
    second_min_value = None
    for r in successful_runs:
        if r['final_value'] > min_value:
            second_min_value = r['final_value']
            break
            
    second_best_patterns = []
    if second_min_value is not None:
        second_best_patterns = [r for r in successful_runs if r['final_value'] == second_min_value]

    # 4. レポートコンテンツの構築
    filepath = os.path.join(output_dir, "_permutation_summary.txt")
    objective_label = objective_mode.title()
    
    content = [
        "==========================================================================",
        f"        Permutation Analysis Summary (Objective: {objective_label})        ",
        "==========================================================================",
        f"\nTotal permutations run: {len(results_list)}",
        f"Successful runs: {len(successful_runs)}",
        f"Metric minimized: {objective_mode.upper()}",
        f"Note: If Optimization Mode is 'waste', this value represents the waste minimization."
    ]

    # --- Best Pattern(s) ---
    content.append("\n" + "="*80)
    content.append(f"🥇 BEST PATTERN(S): {objective_label} = {min_value}")
    content.append("="*80)
    
    for i, pattern in enumerate(best_patterns):
        content.append(f"\n--- Rank 1 Pattern {i+1} (Run: {pattern['run_name']}) ---")
        content.append(f"  Final Objective Value ({objective_label}): {pattern['final_value']}")
        # --- 変更: None を 'N/A' として表示 ---
        content.append(f"  Total Operations: {pattern.get('total_operations', 'N/A')}")
        content.append(f"  Total Reagent Units: {pattern.get('total_reagents', 'N/A')}")
        content.append(f"  Total Waste: {pattern.get('total_waste', 'N/A')}")
        # --- 変更ここまで ---
        content.append(f"  Elapsed Time: {pattern['elapsed_time']:.2f} sec")
        content.append("  Target Permutation Structure:")
        for target in pattern['targets']:
            ratios_str = ', '.join(map(str, target['ratios']))
            factors_str = ', '.join(map(str, target['factors']))
            content.append(f"    - {target['name']}: Ratios=[{ratios_str}], Factors=[{factors_str}]")

    # --- Second Best Pattern(s) ---
    if second_min_value is not None:
        content.append("\n" + "="*80)
        content.append(f"🥈 SECOND BEST PATTERN(S): {objective_label} = {second_min_value}")
        content.append("="*80)
        
        for i, pattern in enumerate(second_best_patterns):
            content.append(f"\n--- Rank 2 Pattern {i+1} (Run: {pattern['run_name']}) ---")
            content.append(f"  Final Objective Value ({objective_label}): {pattern['final_value']}")
            # --- 変更: None を 'N/A' として表示 ---
            content.append(f"  Total Operations: {pattern.get('total_operations', 'N/A')}")
            content.append(f"  Total Reagent Units: {pattern.get('total_reagents', 'N/A')}")
            content.append(f"  Total Waste: {pattern.get('total_waste', 'N/A')}")
            # --- 変更ここまで ---
            content.append(f"  Elapsed Time: {pattern['elapsed_time']:.2f} sec")
            content.append("  Target Permutation Structure:")
            for target in pattern['targets']:
                ratios_str = ', '.join(map(str, target['ratios']))
                factors_str = ', '.join(map(str, target['factors']))
                content.append(f"    - {target['name']}: Ratios=[{ratios_str}], Factors=[{factors_str}]")
    else:
        content.append("\nNo second best permutation found.")

    # 5. ファイル保存
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        print(f"\nPermutation summary saved to: {filepath}")
    except IOError as e:
        print(f"\nError saving permutation summary file: {e}")