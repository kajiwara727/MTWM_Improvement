import os


def _calculate_and_save_summary(
    run_results, output_dir, filename_prefix, title_prefix, objective_mode
):
    filepath = os.path.join(output_dir, f"_{filename_prefix}_summary.txt")

    content = [
        "==================================================",
        f"      Summary of All {title_prefix} Simulation Runs       ",
        "==================================================",
        f"\nTotal simulations executed: {len(run_results)}\n",
    ]

    for run_result in run_results:
        content.append("-" * 50)
        content.append(f"Run Name: {run_result['run_name']}")
        content.append(f"  -> Execution Time: {run_result['elapsed_time']:.2f} seconds")

        if run_result["final_value"] is not None:
            mode_lower = objective_mode.lower()
            objective_label = "Final Objective Value"
            if mode_lower == "waste":
                objective_label = "Minimum Waste Found"
            elif mode_lower == "operations":
                objective_label = "Minimum Operations Found"
            elif mode_lower == "reagents":
                objective_label = "Minimum Reagents Found"

            content.append(f"  -> {objective_label}: {run_result['final_value']}")
            content.append(
                f"  -> Total Operations: {run_result.get('total_operations', 'N/A')}"
            )
            content.append(
                f"  -> Total Reagent Units: {run_result.get('total_reagents', 'N/A')}"
            )
            content.append(
                f"  -> Total Waste Generated: {run_result.get('total_waste', 'N/A')}"
            )
        else:
            content.append("  -> No solution was found for this configuration.")

        if "config" in run_result and run_result["config"]:
            content.append("  -> Target Configurations:")
            for target_idx, config in enumerate(run_result["config"]):
                ratios_str = ", ".join(map(str, config["ratios"]))
                content.append(f"    - Target {target_idx+1}: Ratios = [{ratios_str}]")
            content.append("")

    successful_runs = [res for res in run_results if res["final_value"] is not None]
    num_successful_runs = len(successful_runs)
    mode_label = objective_mode.title()

    if num_successful_runs > 0:
        def sum_metric_safe(metric_key):
            return sum(
                run.get(metric_key, 0)
                for run in successful_runs
                if run.get(metric_key) is not None
                and isinstance(run.get(metric_key), (int, float))
            )

        # 各指標の合計値を計算
        total_objective_value = sum_metric_safe("final_value")
        total_waste = sum_metric_safe("total_waste")
        total_operations = sum_metric_safe("total_operations")
        total_reagents = sum_metric_safe("total_reagents")

        # 平均値を計算
        avg_objective_value = total_objective_value / num_successful_runs
        avg_waste = total_waste / num_successful_runs
        avg_operations = total_operations / num_successful_runs
        avg_reagents = total_reagents / num_successful_runs
        # --- ★★★ ---

        content.append("\n" + "=" * 50)
        content.append(
            f"        Average Results (based on {num_successful_runs} successful runs)        "
        )
        content.append("=" * 50)
        content.append(
            f"Average Objective Value ({mode_label}): {avg_objective_value:.2f}"
        )
        content.append(f"Average Total Waste: {avg_waste:.2f}")
        content.append(f"Average Total Operations: {avg_operations:.2f}")
        content.append(f"Average Total Reagent Units: {avg_reagents:.2f}")
        content.append("=" * 50)
    else:
        content.append("\nNo successful runs found to calculate averages.")

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(content))
        print("\n" + "=" * 60)
        print(f"SUCCESS: A summary of all {title_prefix} runs has been saved to:")
        print(f"  -> {filepath}")
        print("=" * 60)
        return True
    except IOError as e:
        print(f"\nError saving {title_prefix} run summary file: {e}")
        return False


def save_random_run_summary(run_results, output_dir):
    objective_mode = "waste"
    if run_results and "objective_mode" in run_results[0]:
        objective_mode = run_results[0]["objective_mode"]

    _calculate_and_save_summary(
        run_results, output_dir, "random_runs", "Random", objective_mode
    )


def save_comparison_summary(run_results, output_dir, objective_mode):
    _calculate_and_save_summary(
        run_results, output_dir, "comparison_runs", "Comparison", objective_mode
    )


def save_permutation_summary(run_results, output_dir, objective_mode):
    # 1. 成功した実行のみをフィルタリング
    successful_runs = [res for res in run_results if res["final_value"] is not None]

    if not successful_runs:
        print("\n[Permutation Summary] No successful runs found.")
        return

    # 2. 目的値でソート (昇順)
    successful_runs.sort(key=lambda x: x["final_value"])
    min_objective_value = successful_runs[0]["final_value"]

    # 3. ベストパターンを抽出
    best_runs = [
        run for run in successful_runs if run["final_value"] == min_objective_value
    ]

    # 4. セカンドベストパターンを抽出
    second_min_objective_value = None
    for run in successful_runs:
        if run["final_value"] > min_objective_value:
            second_min_objective_value = run["final_value"]
            break

    second_best_runs = []
    if second_min_objective_value is not None:
        second_best_runs = [
            run
            for run in successful_runs
            if run["final_value"] == second_min_objective_value
        ]

    # 5. レポートコンテンツの構築
    filepath = os.path.join(output_dir, "_permutation_summary.txt")
    objective_label = objective_mode.title()

    content = [
        "==========================================================================",
        f"        Permutation Analysis Summary (Objective: {objective_label})        ",
        "==========================================================================",
        f"\nTotal permutations run: {len(run_results)}",
        f"Successful runs: {len(successful_runs)}",
        f"Metric minimized: {objective_mode.upper()}",
        f"Note: If Optimization Mode is 'waste', this value represents the waste minimization.",
    ]

    # --- ベストパターン ---
    content.append("\n" + "=" * 80)
    content.append(f"🥇 BEST PATTERN(S): {objective_label} = {min_objective_value}")
    content.append("=" * 80)

    for i, best_run in enumerate(best_runs):
        content.append(f"\n--- Rank 1 Pattern {i+1} (Run: {best_run['run_name']}) ---")
        content.append(
            f"  Final Objective Value ({objective_label}): {best_run['final_value']}"
        )
        content.append(f"  Total Operations: {best_run.get('total_operations', 'N/A')}")
        content.append(
            f"  Total Reagent Units: {best_run.get('total_reagents', 'N/A')}"
        )
        content.append(f"  Total Waste: {best_run.get('total_waste', 'N/A')}")
        content.append(f"  Elapsed Time: {best_run['elapsed_time']:.2f} sec")
        content.append("  Target Permutation Structure:")
        for target_config in best_run["targets"]:
            ratios_str = ", ".join(map(str, target_config["ratios"]))
            factors_str = ", ".join(map(str, target_config["factors"]))
            content.append(
                f"    - {target_config['name']}: Ratios=[{ratios_str}], Factors=[{factors_str}]"
            )

    # --- セカンドベストパターン ---
    if second_min_objective_value is not None:
        content.append("\n" + "=" * 80)
        content.append(
            f"🥈 SECOND BEST PATTERN(S): {objective_label} = {second_min_objective_value}"
        )
        content.append("=" * 80)

        for i, second_best_run in enumerate(second_best_runs):
            content.append(
                f"\n--- Rank 2 Pattern {i+1} (Run: {second_best_run['run_name']}) ---"
            )
            content.append(
                f"  Final Objective Value ({objective_label}): {second_best_run['final_value']}"
            )
            content.append(
                f"  Total Operations: {second_best_run.get('total_operations', 'N/A')}"
            )
            content.append(
                f"  Total Reagent Units: {second_best_run.get('total_reagents', 'N/A')}"
            )
            content.append(
                f"  Total Waste: {second_best_run.get('total_waste', 'N/A')}"
            )
            content.append(f"  Elapsed Time: {second_best_run['elapsed_time']:.2f} sec")
            content.append("  Target Permutation Structure:")
            for target_config in second_best_run["targets"]:
                ratios_str = ", ".join(map(str, target_config["ratios"]))
                factors_str = ", ".join(map(str, target_config["factors"]))
                content.append(
                    f"    - {target_config['name']}: Ratios=[{ratios_str}], Factors=[{factors_str}]"
                )
    else:
        content.append("\nNo second best permutation found.")

    # 6. ファイル保存
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(content))
        print(f"\nPermutation summary saved to: {filepath}")
    except IOError as e:
        print(f"\nError saving permutation summary file: {e}")
