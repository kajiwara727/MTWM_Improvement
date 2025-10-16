# reporting/analyzer.py
import os

class PreRunAnalyzer:
    """
    最適化の実行前に、構築された混合ツリーの構造やP値、共有可能性などの
    事前チェックを行い、その結果をレポートファイルとして保存するクラス。
    これにより、意図した通りの問題設定になっているかをデバッグしやすくなります。
    """
    def __init__(self, problem, tree_structures):
        """
        コンストラクタ。

        Args:
            problem (MTWMProblem): 最適化問題の定義オブジェクト。
            tree_structures (list): DFMMによって生成されたツリー構造。
        """
        self.problem = problem
        self.tree_structures = tree_structures

    def generate_report(self, output_dir):
        """
        事前分析レポートを生成し、指定されたディレクトリに保存します。

        Args:
            output_dir (str): レポートファイルを保存するディレクトリのパス。
        """
        # レポートファイルのパスを構築
        filepath = os.path.join(output_dir, "_pre_run_analysis.txt")
        content = []
        # 各セクションのコンテンツを構築して結合
        content.extend(self._build_tree_structure_section())
        content.append("\n\n" + "="*55 + "\n")
        content.extend(self._build_p_values_section())
        content.append("\n\n" + "="*55 + "\n")
        content.extend(self._build_sharing_potential_section())

        try:
            # ファイルに書き込み
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write('\n'.join(content))
            print(f"Pre-run analysis report saved to: {filepath}")
        except IOError as e:
            # エラーハンドリング
            print(f"Error saving pre-run analysis report: {e}")

    def _build_tree_structure_section(self):
        """セクション1: DFMMによって構築されたツリーの接続情報レポートを構築する。"""
        content = ["--- Section 1: Generated Tree Structures (Node Connections) ---"]
        for m, tree in enumerate(self.tree_structures):
            target_info = self.problem.targets_config[m]
            content.append(f"\n[Target: {target_info['name']}] (Factors: {target_info['factors']})")
            if not tree:
                content.append("  No nodes generated for this target.")
                continue

            # ノードIDでソートして、表示順を安定させる
            sorted_nodes = sorted(tree.items())
            for node_id, node_data in sorted_nodes:
                level, k = node_id
                # 子ノードの情報を文字列にフォーマット
                children_str = ", ".join([f"v_{c[0]}_{c[1]}" for c in sorted(node_data['children'])])
                content.append(f"  Node v_m{m}_l{level}_k{k} <-- [{children_str if children_str else 'Reagents Only'}]")
        return content

    def _build_p_values_section(self):
        """セクション2: 計算された各ノードのP値の検証レポートを構築する。"""
        content = ["--- Section 2: Calculated P-values per Node ---"]
        for m, p_tree in enumerate(self.problem.p_values):
            target_info = self.problem.targets_config[m]
            content.append(f"\n[Target: {target_info['name']}] (Ratios: {target_info['ratios']}, Factors: {target_info['factors']})")
            if not p_tree:
                content.append("  No nodes generated for this target.")
                continue
            # ノードIDでソート
            sorted_nodes = sorted(p_tree.items())
            for node_id, p_value in sorted_nodes:
                level, k = node_id
                content.append(f"  Node v_m{m}_l{level}_k{k}: P = {p_value}")
        return content

    def _build_sharing_potential_section(self):
        """セクション3: 共有可能性があるノード間の接続レポートを構築する。"""
        content = ["--- Section 3: Potential Sharing Connections (with P-values for validation) ---"]
        if not self.problem.potential_sources_map:
            content.append("\nNo potential sharing connections were found.")
            return content

        # 供給先ノードでソートして表示
        sorted_destinations = sorted(self.problem.potential_sources_map.keys())
        for dest_node in sorted_destinations:
            sources = self.problem.potential_sources_map[dest_node]
            m_dst, l_dst, k_dst = dest_node
            p_dst = self.problem.p_values[m_dst].get((l_dst, k_dst), 'N/A')
            dest_name = f"v_m{m_dst}_l{l_dst}_k{k_dst}"

            if sources:
                content.append(f"\nNode {dest_name} (P={p_dst}) can potentially receive from:")
                # 供給元とそのP値をリストアップ
                for m_src, l_src, k_src in sources:
                    p_src = self.problem.p_values[m_src].get((l_src, k_src), 'N/A')
                    src_name = f"v_m{m_src}_l{l_src}_k{k_src}"
                    content.append(f"  -> {src_name} (P={p_src})")
        return content