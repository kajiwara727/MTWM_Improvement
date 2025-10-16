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