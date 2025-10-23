# reporting/summary.py
import os

def save_random_run_summary(results_list, output_dir):
    """
    'random' モードで実行された全シミュレーションの結果概要を、
    単一のサマリーファイルに保存します。

    Args:
        results_list (list[dict]): 各ランの結果を格納した辞書のリスト。
        output_dir (str): サマリーファイルを保存するディレクトリのパス。
    """
    # サマリーファイルのフルパスを構築
    filepath = os.path.join(output_dir, "_random_runs_summary.txt")

    # ファイルのヘッダー部分を作成
    content = [
        "==================================================",
        "      Summary of All Random Simulation Runs       ",
        "==================================================",
        f"\nTotal simulations executed: {len(results_list)}\n"
    ]

    # 各実行結果をループして、コンテンツに追加
    for result in results_list:
        content.append("-" * 50)
        content.append(f"Run Name: {result['run_name']}")
        content.append(f"  -> Execution Time: {result['elapsed_time']:.2f} seconds")

        if result['final_value'] is not None:
            # 解が見つかった場合
            content.append(f"  -> Minimum Waste Found: {result['final_value']}")
            content.append(f"  -> Total Operations: {result['total_operations']}")
            content.append(f"  -> Total Reagent Units: {result['total_reagents']}")
        else:
            # 解が見つからなかった場合
            content.append("  -> No solution was found for this configuration.")

        # その実行で使用されたターゲット設定を記録
        content.append("  -> Target Configurations:")
        for i, config in enumerate(result['config']):
            ratios_str = ', '.join(map(str, config['ratios']))
            content.append(f"    - Target {i+1}: Ratios = [{ratios_str}]")
        content.append("") # 見やすくするために空行を追加

    # --- FIX: 平均値の計算と追加ロジック ---
    # 解が見つかったランのみをフィルタリング
    successful_runs = [r for r in results_list if r['final_value'] is not None]
    num_successful_runs = len(successful_runs)

    if num_successful_runs > 0:
        # 各項目の合計を計算
        total_waste = sum(r['final_value'] for r in successful_runs)
        total_operations = sum(r['total_operations'] for r in successful_runs)
        total_reagents = sum(r['total_reagents'] for r in successful_runs)

        # 平均を計算
        avg_waste = total_waste / num_successful_runs
        avg_operations = total_operations / num_successful_runs
        avg_reagents = total_reagents / num_successful_runs

        # 結果をサマリーに追加
        content.append("\n" + "="*50)
        content.append(f"        Average Results (based on {num_successful_runs} successful runs)        ")
        content.append("="*50)
        content.append(f"Average Minimum Waste: {avg_waste:.2f}")
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
        print(f"SUCCESS: A summary of all random runs has been saved to:")
        print(f"  -> {filepath}")
        print("="*60)
    except IOError as e:
        # エラーハンドリング
        print(f"\nError saving random run summary file: {e}")