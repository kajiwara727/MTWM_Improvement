# core/problem.py
import z3
import itertools
from functools import reduce 
import operator 
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
        
        # --- 追加: ピア混合ノードの定義 ---
        # self.forest に依存するため、_define_base_variables の直後に呼び出す
        self.peer_nodes = self._define_peer_mixing_nodes()
        # --- 追加ここまで ---
        
        # ノード間の共有可能性を事前計算
        # (ピアノードを供給元として含める v2 に変更)
        self.potential_sources_map = self._precompute_potential_sources_v2()
        
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

    def _define_peer_mixing_nodes(self):
        """
        【修正】同じP値を持つDFMMノードのペアから「ピア混合ノード（Rノード）」を定義します。
        ただし、両方がリーフノード（P=F）の場合は、無駄なので除外します。
        """
        print(f"Defining potential peer-mixing nodes (1:1 mix)...")
        peer_nodes = []
        
        # DFMMツリー内の全ノードのリストを作成 (IDとノード参照)
        all_dfmm_nodes = []
        for m, tree in enumerate(self.forest):
            for l, nodes in tree.items():
                for k, node in enumerate(nodes):
                    # ルートノード (l=0) は最終生成物なので、混合元にはしない
                    if l == 0:
                        continue
                    all_dfmm_nodes.append(((m, l, k), node))

        # 同じP値を持つノードの全ペアをイテレート
        for (node_a_id, node_a), (node_b_id, node_b) in itertools.combinations(all_dfmm_nodes, 2):
            
            m_a, l_a, k_a = node_a_id
            m_b, l_b, k_b = node_b_id

            p_a = self.p_values[m_a].get((l_a, k_a))
            p_b = self.p_values[m_b].get((l_b, k_b))

            # 1. P値が同じノードペアのみを対象
            if p_a is None or p_a != p_b:
                continue
                
            # --- ここから修正 ---
            # 2. 両方のノードがリーフノード（P=F）かチェック
            f_a = self.targets_config[m_a]['factors'][l_a]
            f_b = self.targets_config[m_b]['factors'][l_b]
            
            is_leaf_a = (p_a == f_a)
            is_leaf_b = (p_b == f_b)

            # もし両方ともリーフノードなら、
            # (例: v_m0_l2_k0 (P=2, F=2) と v_m1_l2_k0 (P=2, F=2))
            # 混合しても無駄なので、このペアのRノードは作成しない
            if is_leaf_a and is_leaf_b:
                continue
            # --- 修正ここまで ---

            # 新しいピアノードの名前を定義
            name = f"R_m{m_a}l{l_a}k{k_a}-m{m_b}l{l_b}k{k_b}"
            
            # このピアノードを定義
            peer_node = {
                'name': name,
                'source_a_id': node_a_id,
                'source_b_id': node_b_id,
                'p_value': p_a,
                # このノードの比率変数 (r)
                'ratio_vars': [z3.Int(f"R_{name}_t{t}") for t in range(self.num_reagents)],
                # このノードへの入力 (1:1混合のため、ミキサーサイズ2)
                'input_vars': {
                    'from_a': z3.Int(f"w_peer_a_to_{name}"),
                    'from_b': z3.Int(f"w_peer_b_to_{name}")
                }
            }
            peer_nodes.append(peer_node)
        
        print(f"  -> Found {len(peer_nodes)} potential peer-mixing combinations.")
        return peer_nodes

    def _precompute_potential_sources_v2(self):
        """
        【変更】全てのノードペア間の接続可能性を事前に判定します。
        供給元(src)として、DFMMノードに加えて新しいピアノード(Rノード)も考慮します。
        """
        source_map = {}
        # 1. 供給先(dst)は常にDFMMノード
        all_dest_nodes = [(m, l, k) for m, tree in enumerate(self.forest) for l, nodes in tree.items() for k in range(len(nodes))]

        # 2. 供給元(src)はDFMMノード
        all_dfmm_sources = list(all_dest_nodes)
        
        # 3. 供給元(src)はピアノード (Rノード)
        # ('R', index, 0) というタプルでRノードを表す
        all_peer_sources = [('R', i, 0) for i in range(len(self.peer_nodes))]
        
        all_sources = all_dfmm_sources + all_peer_sources

        # 全てのノードペアの組み合わせについて接続可能性をチェック
        for (m_dst, l_dst, k_dst), (m_src, l_src, k_src) in itertools.product(all_dest_nodes, all_sources):
            
            p_dst = self.p_values[m_dst][(l_dst, k_dst)]
            f_dst = self.targets_config[m_dst]['factors'][l_dst]

            # --- 供給元(src)の情報を取得 ---
            if m_src == 'R':
                # 供給元がピアノード(R)の場合
                peer_node = self.peer_nodes[l_src] # l_src は Rノードのindex
                p_src = peer_node['p_value']
                # ピアノードの「レベル」は、その親のレベルとみなす
                l_src_eff = max(peer_node['source_a_id'][1], peer_node['source_b_id'][1])
                # Rノードは自分自身には供給できない (Rノードは供給先に含まれていないため自動的に満たされる)
            
            else:
                # 供給元がDFMMノードの場合
                p_src = self.p_values[m_src][(l_src, k_src)]
                l_src_eff = l_src
                # 1. 自分自身を材料にはできない
                if (m_dst, l_dst, k_dst) == (m_src, l_src, k_src):
                    continue

            # --- 接続条件 ---
            
            # 2. 供給元(src)は供給先(dst)より下位のレベルでなければならない。
            #    ただし、供給元が最終生成物(rootノード, l_src=0)の場合は例外的に許可する。
            is_valid_level_connection = (l_src_eff > l_dst) or (l_src_eff == 0)
            if not is_valid_level_connection:
                continue

            # 3. レベル差が設定された上限を超えてはならない
            if MAX_LEVEL_DIFF is not None and l_src_eff > l_dst + MAX_LEVEL_DIFF: continue

            # 4. 濃度保存則を満たすためのP値の整数除算条件
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
            
            # --- 変更: 異なるツリー間、またはRノードからの共有 ---
            else:
                if m_src == 'R':
                    # 【新規】ピアノード(R)からの共有
                    key = f"from_R_idx{l_src}" # l_srcはRノードのindex
                    name = f"w_inter_from_R{l_src}_to_m{m_dst}l{l_dst}k{k_dst}"
                    inter_vars[key] = z3.Int(name)
                else:
                    # 【既存】異なるツリー間での共有 (inter-sharing)
                    key = f"from_m{m_src}_l{l_src}k{k_src}"
                    name = f"w_inter_from_m{m_src}{l_src}k{k_src}_to_m{m_dst}l{l_dst}k{k_dst}"
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