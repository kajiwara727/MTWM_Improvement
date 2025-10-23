# reporting/reporter.py
import os
import z3
from config import MAX_SHARING_VOLUME, MAX_LEVEL_DIFF, MAX_MIXER_SIZE
from .visualizer import SolutionVisualizer

class SolutionReporter:
    """
    Z3ソルバーが見つけた解（モデル）を解析し、人間が読める形式の
    テキストベースのレポートを生成し、可視化モジュールを呼び出すクラス。
    """

    def __init__(self, problem, model, objective_mode="waste"):
        """
        コンストラクタ。

        Args:
            problem (MTWMProblem): 最適化問題の定義オブジェクト。
            model (z3.ModelRef): Z3ソルバーが見つけた解のモデル。
            objective_mode (str): 最適化の目的 ('waste' or 'operations')。
        """
        self.problem = problem
        self.model = model
        self.objective_mode = objective_mode

    def generate_full_report(self, min_value, elapsed_time, output_dir):
        """
        解の分析、コンソールへのサマリー出力、ファイルへの詳細レポート保存、
        そして結果の可視化という一連のレポート生成プロセスを実行します。
        """
        analysis_results = self.analyze_solution() # <--- analyze_solution() の結果を取得

        # --- FIX: Or-ToolsのAnalyzeで発生する総廃棄物量の不整合を修正 ---
        # 目的が 'waste' の場合、分析結果の合計 (results["total_waste"]) ではなく、
        # 最適化で得られた目的関数の最小値 (min_value) を採用する。
        if self.objective_mode == 'waste' and analysis_results is not None:
             # min_valueは float の可能性もあるため、int() に変換
             analysis_results['total_waste'] = int(min_value)
        # --- END FIX ---

        self._print_console_summary(analysis_results, min_value, elapsed_time)

    def report_from_checkpoint(self, analysis, value, output_dir):
        """
        チェックポイントから読み込んだ既存の解データを基にレポートを生成します。
        モデルを再構築して可視化も試みます。

        Args:
            analysis (dict): チェックポイントに保存されていた分析結果。
            value (int): チェックポイントに保存されていた目的関数の値。
            output_dir (str): レポートと画像を保存するディレクトリのパス。
        """
        from z3_solver import Z3Solver # 循環参照を避けるため、メソッド内でインポート

        # テキストレポートは保存されたデータから生成
        self._print_console_summary(analysis, value, 0)
        self._save_summary_to_file(analysis, value, 0, output_dir)

        print("\nAttempting to generate visualization from checkpoint data...")
        # 可視化のために、保存された値と等しいという制約を追加してモデルを再構築
        temp_solver = Z3Solver(self.problem, objective_mode=self.objective_mode)
        temp_solver.opt.add(temp_solver.objective_variable == value)

        if temp_solver.check() == z3.sat:
            # モデルが見つかれば可視化を実行
            checkpoint_model = temp_solver.get_model()
            visualizer = SolutionVisualizer(self.problem, checkpoint_model)
            visualizer.visualize_solution(output_dir)
            print(f"   Visualization successfully generated from checkpoint.")
        else:
            print("\nVisualization could not be generated because the model could not be recreated.")

    def analyze_solution(self):
        """
        Z3のモデルを解析し、総操作回数、総試薬使用量、各ノードの混合詳細など、
        レポートに必要な情報を抽出して辞書形式で返します。
        """
        if not self.model: return None
        results = {"total_operations": 0, "total_reagent_units": 0, "total_waste": 0, "reagent_usage": {}, "nodes_details": []}
        # 全てのノードをイテレート
        for tree_idx, tree in enumerate(self.problem.forest):
            for level, nodes in tree.items():
                for node_idx, node in enumerate(nodes):
                    # このノードへの総入力が0より大きい場合、アクティブなノードと見なす
                    total_input = self.model.eval(z3.Sum(self._get_input_vars(node))).as_long()
                    if total_input == 0: continue

                    results["total_operations"] += 1
                    # 試薬使用量を集計
                    reagent_vals = [self.model.eval(r).as_long() for r in node['reagent_vars']]
                    for r_idx, val in enumerate(reagent_vals):
                        if val > 0:
                            results["total_reagent_units"] += val
                            results["reagent_usage"][r_idx] = results["reagent_usage"].get(r_idx, 0) + val
                    # 廃棄物量を集計
                    if 'waste_var' in node:
                         results["total_waste"] += self.model.eval(node['waste_var']).as_long()
                    # 各ノードの詳細情報を記録
                    results["nodes_details"].append({
                        "target_id": tree_idx, "level": level, "name": f"v_m{tree_idx}_l{level}_k{node_idx}",
                        "total_input": total_input,
                        "ratio_composition": [self.model.eval(r).as_long() for r in node['ratio_vars']],
                        "mixing_str": self._generate_mixing_description(node, tree_idx)
                    })
        return results

    def _get_input_vars(self, node):
        """ノードへの全入力（試薬、内部共有、外部共有）の変数をリストで返すヘルパー関数。"""
        return (node.get('reagent_vars', []) +
                list(node.get('intra_sharing_vars', {}).values()) +
                list(node.get('inter_sharing_vars', {}).values()))

    def _generate_mixing_description(self, node, tree_idx):
        """ノードの混合内容を説明する文字列（例: "5 x Reagent1 + 3 x v_m0_l2_k0"）を生成する。"""
        desc = []
        # 試薬の投入
        for r_idx, r_var in enumerate(node.get('reagent_vars', [])):
            if (val := self.model.eval(r_var).as_long()) > 0:
                desc.append(f"{val} x Reagent{r_idx+1}")
        # 同じツリー内からの共有
        for key, w_var in node.get('intra_sharing_vars', {}).items():
            if (val := self.model.eval(w_var).as_long()) > 0:
                desc.append(f"{val} x v_m{tree_idx}_{key.replace('from_', '')}")
        # 異なるツリーからの共有
        for key, w_var in node.get('inter_sharing_vars', {}).items():
            if (val := self.model.eval(w_var).as_long()) > 0:
                m_src, lk_src = key.split('_l')
                desc.append(f"{val} x v_{m_src.replace('from_m', 'm')}_l{lk_src}")
        return ' + '.join(desc)

    def _print_console_summary(self, results, min_value, elapsed_time):
        """最適化結果のサマリーをコンソールに出力する。"""
        time_str = f"(in {elapsed_time:.2f} sec)" if elapsed_time > 0 else "(from checkpoint)"
        print(f"\n<Improvement>Optimal Solution Found {time_str}")
        if self.objective_mode == "waste":
            objective_str = "Minimum Total Waste"
        elif self.objective_mode == "operations":
            objective_str = "Minimum Operations"
        else:
            objective_str = "Minimum Total Reagents"
        print(f"{objective_str}: {min_value}")
        print("="*18 + " SUMMARY " + "="*18)
        if results:
            print(f"Total mixing operations: {results['total_operations']}")
            print(f"Total waste generated: {results['total_waste']}")
            print(f"Total reagent units used: {results['total_reagent_units']}")
            print("\nReagent usage breakdown:")
            for r_idx in sorted(results['reagent_usage'].keys()):
                print(f"  Reagent {r_idx+1}: {results['reagent_usage'][r_idx]} unit(s)")
        print("="*45)

    def _save_summary_to_file(self, results, min_value, elapsed_time, output_dir):
        """詳細な結果レポートをテキストファイルに保存する。"""
        filepath = os.path.join(output_dir, 'summary.txt')
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                content = self._build_summary_file_content(results, min_value, elapsed_time, output_dir)
                f.write('\n'.join(content))
            print(f"\nResults summary saved to: {filepath}")
        except IOError as e:
            print(f"\nError saving results to file: {e}")

    def _build_summary_file_content(self, results, min_value, elapsed_time, dir_name):
        """ファイルに書き込むための全コンテンツを文字列リストとして構築する。"""
        if self.objective_mode == "waste":
            objective_str = "Minimum Total Waste"
        elif self.objective_mode == "operations":
            objective_str = "Minimum Operations"
        else:
            objective_str = "Minimum Total Reagents"
        content = [
            "="*40, f"Optimization Results for: {os.path.basename(dir_name)}", "="*40,
            f"\nSolved in {elapsed_time:.2f} seconds." if elapsed_time > 0 else "\nLoaded from checkpoint.",
            "\n--- Target Configuration ---"
        ]
        # ターゲット設定の記録
        for i, target in enumerate(self.problem.targets_config):
            content.extend([f"Target {i+1}:", f"  Ratios: {' : '.join(map(str, target['ratios']))}", f"  Factors: {target['factors']}"])
        # 最適化設定の記録
        content.extend([
            "\n--- Optimization Settings ---",
            f"Optimization Mode: {self.objective_mode.upper()}",
            f"Max Sharing Volume: {MAX_SHARING_VOLUME or 'No limit'}",
            f"Max Level Difference: {MAX_LEVEL_DIFF or 'No limit'}",
            f"Max Mixer Size: {MAX_MIXER_SIZE}",
            "-"*28,
            f"\n{objective_str}: {min_value}"
        ])
        # 結果サマリー
        if results:
            content.extend([
                f"Total mixing operations: {results['total_operations']}",
                f"Total waste generated: {results['total_waste']}",
                f"Total reagent units used: {results['total_reagent_units']}",
                "\n--- Reagent Usage Breakdown ---"
            ])
            for t in sorted(results['reagent_usage'].keys()):
                content.append(f"  Reagent {t+1}: {results['reagent_usage'][t]} unit(s)")
            content.append("\n\n--- Mixing Process Details ---")
            # 混合プロセスの詳細
            current_target = -1
            for detail in results["nodes_details"]:
                if detail["target_id"] != current_target:
                    current_target = detail["target_id"]
                    content.append(f"\n[Target {current_target + 1} ({self.problem.targets_config[current_target]['name']})]")
                content.extend([
                    f" Level {detail['level']}:",
                    f"   Node {detail['name']}: total_input = {detail['total_input']}",
                    f"     Ratio composition: {detail['ratio_composition']}",
                    f"     Mixing: {detail['mixing_str']}" if detail['mixing_str'] else "     (No mixing actions for this node)"
                ])
        return content