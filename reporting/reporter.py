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
            model (z3.ModelRef or OrToolsModelAdapter): Z3/Or-Toolsの解のモデル。
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
        analysis_results = self.analyze_solution() 

        if self.objective_mode == 'waste' and analysis_results is not None:
             analysis_results['total_waste'] = int(min_value)

        self._print_console_summary(analysis_results, min_value, elapsed_time)
        
        self._save_summary_to_file(analysis_results, min_value, elapsed_time, output_dir)
        if self.model:
            # 可視化クラスを呼び出してグラフを生成
            # (注: 可視化はRノードに対応していません)
            visualizer = SolutionVisualizer(self.problem, self.model)
            visualizer.visualize_solution(output_dir)

    def analyze_solution(self):
        """
        【変更】モデルを解析し、DFMMノードとピアRノードの両方の情報を
        抽出して辞書形式で返します。
        """
        if not self.model: return None
        results = {"total_operations": 0, "total_reagent_units": 0, "total_waste": 0, "reagent_usage": {}, "nodes_details": []}
        
        # 1. DFMMノード (self.problem.forest) をイテレート
        for tree_idx, tree in enumerate(self.problem.forest):
            for level, nodes in tree.items():
                for node_idx, node in enumerate(nodes):
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
        
        # 2. ピアRノード (self.problem.peer_nodes) をイテレート
        for i, peer_node in enumerate(self.problem.peer_nodes):
            total_input = self.model.eval(z3.Sum(list(peer_node['input_vars'].values()))).as_long()
            if total_input == 0: continue
            
            results["total_operations"] += 1
            # (試薬使用はなし)
            if 'waste_var' in peer_node:
                 results["total_waste"] += self.model.eval(peer_node['waste_var']).as_long()
            
            # 混合文字列を生成 (1:1 mix)
            m_a, l_a, k_a = peer_node['source_a_id']
            name_a = f"v_m{m_a}_l{l_a}_k{k_a}"
            m_b, l_b, k_b = peer_node['source_b_id']
            name_b = f"v_m{m_b}_l{l_b}_k{k_b}"
            mixing_str = f"1 x {name_a} + 1 x {name_b}"
            
            # レベルは親の平均-0.5としてソートしやすくする
            level_eff = (l_a + l_b) / 2.0 - 0.5 

            results["nodes_details"].append({
                "target_id": -1, # ピアノード用の特別なID
                "level": level_eff, 
                "name": peer_node['name'],
                "total_input": total_input,
                "ratio_composition": [self.model.eval(r).as_long() for r in peer_node['ratio_vars']],
                "mixing_str": mixing_str
            })

        # レベル順にソートしてレポートの順序を整える
        results["nodes_details"].sort(key=lambda x: (x['target_id'], x['level']))

        return results

    def _get_input_vars(self, node):
        """ノードへの全入力（試薬、内部共有、外部共有）の変数をリストで返すヘルパー関数。"""
        # (DFMMノード用、変更不要)
        return (node.get('reagent_vars', []) +
                list(node.get('intra_sharing_vars', {}).values()) +
                list(node.get('inter_sharing_vars', {}).values()))

    def _generate_mixing_description(self, node, tree_idx):
        """【変更】ノードの混合内容を説明する文字列を生成する。Rノードからの入力を考慮。"""
        desc = []
        # 試薬の投入
        for r_idx, r_var in enumerate(node.get('reagent_vars', [])):
            if (val := self.model.eval(r_var).as_long()) > 0:
                desc.append(f"{val} x Reagent{r_idx+1}")
        # 同じツリー内からの共有
        for key, w_var in node.get('intra_sharing_vars', {}).items():
            if (val := self.model.eval(w_var).as_long()) > 0:
                desc.append(f"{val} x v_m{tree_idx}_{key.replace('from_', '')}")
        
        # 異なるツリー または Rノードからの共有
        for key, w_var in node.get('inter_sharing_vars', {}).items():
            if (val := self.model.eval(w_var).as_long()) > 0:
                
                if key.startswith('from_R_idx'):
                    # 【新規】Rノードからの入力
                    idx = int(key.replace('from_R_idx', ''))
                    # problem オブジェクトからRノードの名前を取得
                    peer_node_name = self.problem.peer_nodes[idx]['name']
                    desc.append(f"{val} x {peer_node_name}")
                
                else:
                    # 【既存】異なるツリーからの入力
                    m_src, lk_src = key.split('_l')
                    desc.append(f"{val} x v_{m_src.replace('from_m', 'm')}_l{lk_src}")
                    
        return ' + '.join(desc)

    def _print_console_summary(self, results, min_value, elapsed_time):
        # (変更不要 -> チェックポイントロジックを削除)
        time_str = f"(in {elapsed_time:.2f} sec)"
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
        # (変更不要)
        filepath = os.path.join(output_dir, 'summary.txt')
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                content = self._build_summary_file_content(results, min_value, elapsed_time, output_dir)
                f.write('\n'.join(content))
            print(f"\nResults summary saved to: {filepath}")
        except IOError as e:
            print(f"\nError saving results to file: {e}")

    def _build_summary_file_content(self, results, min_value, elapsed_time, dir_name):
        """【変更】Rノードの表示に対応。チェックポイントロジックを削除。"""
        if self.objective_mode == "waste":
            objective_str = "Minimum Total Waste"
        elif self.objective_mode == "operations":
            objective_str = "Minimum Operations"
        else:
            objective_str = "Minimum Total Reagents"
        content = [
            "="*40, f"Optimization Results for: {os.path.basename(dir_name)}", "="*40,
            f"\nSolved in {elapsed_time:.2f} seconds.",
            "\n--- Target Configuration ---"
        ]
        # ( ... 既存の設定記録ロジック ... )
        for i, target in enumerate(self.problem.targets_config):
            content.extend([f"Target {i+1}:", f"  Ratios: {' : '.join(map(str, target['ratios']))}", f"  Factors: {target['factors']}"])
        content.extend([
            "\n--- Optimization Settings ---",
            f"Optimization Mode: {self.objective_mode.upper()}",
            f"Max Sharing Volume: {MAX_SHARING_VOLUME or 'No limit'}",
            f"Max Level Difference: {MAX_LEVEL_DIFF or 'No limit'}",
            f"Max Mixer Size: {MAX_MIXER_SIZE}",
            "-"*28,
            f"\n{objective_str}: {min_value}"
        ])
        
        # 結果サマリー (変更不要)
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
            current_target = -2 # -1 (ピア) と 0 (ターゲット1) を区別
            
            for detail in results["nodes_details"]:
                if detail["target_id"] != current_target:
                    current_target = detail["target_id"]
                    if current_target == -1:
                        content.append(f"\n[Peer Mixing Nodes (1:1 Mix)]")
                    else:
                        content.append(f"\n[Target {current_target + 1} ({self.problem.targets_config[current_target]['name']})]")
                
                level_str = f"{detail['level']}" if isinstance(detail['level'], int) else f"{detail['level']:.1f}"
                
                content.extend([
                    f" Level {level_str}:",
                    f"   Node {detail['name']}: total_input = {detail['total_input']}",
                    f"     Ratio composition: {detail['ratio_composition']}",
                    f"     Mixing: {detail['mixing_str']}" if detail['mixing_str'] else "     (No mixing actions for this node)"
                ])
        return content