# core/problem.py
import z3
import itertools
from config import MAX_LEVEL_DIFF

class MTWMProblem:
    """
    MTWM (Multi-Target Waste Minimization) 問題の構造を定義、管理するクラス。
    最適化に必要な変数（液量、比率など）をz3の変数として定義し、
    それらの関係性をカプセル化します。
    """
    def __init__(self, targets_config, tree_structures, p_values):
        """
        コンストラクタ。
        事前計算されたツリー構造とP値を受け取り、z3の変数を初期化します。

        Args:
            targets_config (list): ターゲット設定のリスト。
            tree_structures (list): DFMMで生成されたツリー構造のリスト。
            p_values (list): 各ノードのP値のリスト。
        """
        self.targets_config = targets_config
        self.num_reagents = len(targets_config[0]['ratios']) if targets_config else 0
        self.tree_structures = tree_structures
        self.p_values = p_values

        # 基本変数（ノード、比率、試薬量）を定義
        self.forest = self._define_base_variables()
        # ノード間の共有可能性を事前計算
        self.potential_sources_map = self._precompute_potential_sources()
        # 共有液量を表す変数を定義
        self._define_sharing_variables()

    def _define_base_variables(self):
        """
        混合ノード、濃度（比率）、試薬投入量を表すz3の基本変数を定義します。
        これらの変数が最適化ソルバーによって解かれます。
        """
        forest = []
        for m, tree_structure in enumerate(self.tree_structures):
            tree_data = {}
            # ツリー構造に含まれるレベルをソートして取得
            levels = sorted({l for l, k in tree_structure.keys()})
            for l in levels:
                nodes_at_level = sorted([k for l_node, k in tree_structure.keys() if l_node == l])
                level_nodes = [
                    {
                        # 各ノード（ミキサー）自体を表す変数 (デバッグ用、現在未使用)
                        'node_var': z3.Int(f"v_m{m}_l{l}_k{k}"),
                        # ノード内の各試薬の比率を表す変数
                        'ratio_vars': [z3.Int(f"R_m{m}_l{l}_k{k}_t{t}") for t in range(self.num_reagents)],
                        # ノードに直接投入される各試薬の量を表す変数
                        'reagent_vars': [z3.Int(f"r_m{m}_l{l}_k{k}_t{t}") for t in range(self.num_reagents)]
                    }
                    for k in nodes_at_level
                ]
                tree_data[l] = level_nodes
            forest.append(tree_data)
        return forest

    def _precompute_potential_sources(self):
        """
        全てのノードペア間の接続可能性（中間液を共有できるか）を事前に判定し、
        供給元候補のマップを作成します。これにより、不要な共有変数の生成を防ぎ、
        最適化の効率を向上させます。
        """
        source_map = {}
        # 全てのノードのリストを作成
        all_nodes = [(m, l, k) for m, tree in enumerate(self.forest) for l, nodes in tree.items() for k in range(len(nodes))]

        # 全てのノードペアの組み合わせについて接続可能性をチェック
        for (m_dst, l_dst, k_dst), (m_src, l_src, k_src) in itertools.product(all_nodes, repeat=2):
            # --- 接続条件 ---
            # 1. 供給元(src)は供給先(dst)より下位のレベルでなければならない
            if l_src <= l_dst: continue
            # 2. レベル差が設定された上限を超えてはならない
            if MAX_LEVEL_DIFF is not None and l_src > l_dst + MAX_LEVEL_DIFF: continue

            p_dst = self.p_values[m_dst][(l_dst, k_dst)]
            f_dst = self.targets_config[m_dst]['factors'][l_dst]
            p_src = self.p_values[m_src][(l_src, k_src)]
            # 3. 濃度保存則を満たすためのP値の整数除算条件
            if (p_dst // f_dst) % p_src != 0: continue

            # 条件をすべて満たした場合、供給元候補としてマップに追加
            key = (m_dst, l_dst, k_dst)
            if key not in source_map: source_map[key] = []
            source_map[key].append((m_src, l_src, k_src))

        return source_map

    def _create_sharing_vars_for_node(self, m_dst, l_dst, k_dst):
        """
        単一の供給先ノードに対して、事前計算された供給元候補から
        共有液量を表すz3変数（w_intra, w_inter）の辞書を作成します。
        """
        potential_sources = self.potential_sources_map.get((m_dst, l_dst, k_dst), [])
        intra_vars, inter_vars = {}, {}

        for m_src, l_src, k_src in potential_sources:
            if m_src == m_dst:
                # 同じツリー内での共有 (intra-sharing)
                key = f"from_l{l_src}k{k_src}"
                name = f"w_intra_m{m_dst}_from_l{l_src}k{k_src}_to_l{l_dst}k{k_dst}"
                intra_vars[key] = z3.Int(name)
            else:
                # 異なるツリー間での共有 (inter-sharing)
                key = f"from_m{m_src}_l{l_src}k{k_src}"
                name = f"w_inter_from_m{m_src}l{l_src}k{k_src}_to_m{m_dst}l{l_dst}k{k_dst}"
                inter_vars[key] = z3.Int(name)
        return intra_vars, inter_vars

    def _define_sharing_variables(self):
        """
        全てのノードに対して共有変数を定義し、各ノードのデータ構造に割り当てます。
        """
        for m_dst, tree_dst in enumerate(self.forest):
            for l_dst, nodes_dst in tree_dst.items():
                for k_dst, node in enumerate(nodes_dst):
                    intra, inter = self._create_sharing_vars_for_node(m_dst, l_dst, k_dst)
                    node['intra_sharing_vars'] = intra
                    node['inter_sharing_vars'] = inter