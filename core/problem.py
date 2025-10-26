import z3  # SMTソルバー Z3 (注: 変数定義にのみ使われ、実際の求解はOr-Tools)
import itertools
from config import MAX_LEVEL_DIFF  # config.py から最大レベル差をインポート

from utils import (     # 変更後
    create_dfmm_node_name,
    create_intra_key,
    create_inter_key,
    create_peer_key,
)


class MTWMProblem:
    """
    最適化問題を定義するクラス。
    
    DFMMで構築されたツリー構造とP値に基づき、
    ソルバーが必要とする変数（試薬量、中間液量、共有量）や、
    潜在的な共有接続（ピアノード、ツリー間/ツリー内）を定義します。
    
    (注: このクラスは Z3 の変数型を使っていますが、
     OrToolsSolver がこの構造を読み替えて Or-Tools の変数で再構築します)
    """

    def __init__(self, targets_config, tree_structures, p_value_maps):
        """
        コンストラクタ。
        
        Args:
            targets_config (list): ターゲット設定のリスト
            tree_structures (list): DFMMで構築されたツリー構造 (forest_structure)
            p_value_maps (list): DFMMで計算されたP値マップ (p_value_maps)
        """
        self.targets_config = targets_config
        # 試薬の数 (全ターゲットで共通と仮定)
        self.num_reagents = len(targets_config[0]["ratios"]) if targets_config else 0
        self.tree_structures = tree_structures
        self.p_value_maps = p_value_maps
        
        # --- 問題構築のステップ ---
        # 1. DFMMノードの基本変数(比率, 試薬)を定義
        self.forest = self._define_base_variables()
        # 2. ピア(R)ノード (1:1混合ノード) の可能性を探索・定義
        self.peer_nodes = self._define_peer_mixing_nodes()
        # 3. 潜在的な共有元を事前計算 (計算量削減のため)
        self.potential_sources_map = self._precompute_potential_sources_v2()
        # 4. 3に基づき、共有変数 (w_intra, w_inter) を定義
        self._define_sharing_variables()

    def _define_base_variables(self):
        """
        混合ノード、濃度（比率）、試薬投入量を表すz3の基本変数を定義します。
        
        Returns:
            list[dict]: Z3変数を含むノード情報のフォレスト
        """
        forest_data = []
        for target_idx, tree_structure in enumerate(self.tree_structures):
            tree_data = {}
            # このツリーに存在するレベル (0, 1, 2...) をソート
            levels = sorted({lvl for lvl, _ in tree_structure.keys()})

            for level in levels:
                # このレベルに存在するノードインデックス (0, 1...) をソート
                nodes_at_level = sorted(
                    [
                        node_idx
                        for lvl_node, node_idx in tree_structure.keys()
                        if lvl_node == level
                    ]
                )
                level_nodes = []
                for node_idx in nodes_at_level:
                    node_name = create_dfmm_node_name(target_idx, level, node_idx)
                    ratio_name_prefix = f"ratio_{node_name}_r"
                    reagent_name_prefix = f"reagent_vol_{node_name}_r"

                    # (注: ここで Z3 の Int 型変数として定義されている)
                    level_nodes.append(
                        {
                            "node_var": z3.Int(node_name), # ノード本体 (Or-Toolsでは使われない)
                            "ratio_vars": [ # ノードの比率 (R1, R2, ...)
                                z3.Int(f"{ratio_name_prefix}{r_idx}")
                                for r_idx in range(self.num_reagents)
                            ],
                            "reagent_vars": [ # ノードへの試薬投入量 (w_R1, w_R2, ...)
                                z3.Int(f"{reagent_name_prefix}{r_idx}")
                                for r_idx in range(self.num_reagents)
                            ],
                        }
                    )
                tree_data[level] = level_nodes
            forest_data.append(tree_data)
        return forest_data

    def _define_peer_mixing_nodes(self):
        """
        ピア(R)ミキシングノード（P値が同じ2つのDFMMノードを1:1で混合するノード）
        の全組み合わせを探索し、定義します。
        """
        print("Defining potential peer-mixing nodes (1:1 mix)...")
        peer_nodes = [] # 発見したピア(R)ノードのリスト

        # 1. 全DFMMノードのリストを作成 (level 0 (root) は除く)
        all_dfmm_nodes = []
        for target_idx, tree in enumerate(self.forest):
            for level, nodes in tree.items():
                for node_idx, node in enumerate(nodes):
                    if level == 0:
                        continue # rootノードはピア混合の材料にしない
                    all_dfmm_nodes.append(((target_idx, level, node_idx), node))

        # 2. 全DFMMノードのペア (2つの組み合わせ) について総当たり
        for (node_a_id, node_a), (node_b_id, node_b) in itertools.combinations(
            all_dfmm_nodes, 2
        ):
            m_a, l_a, k_a = node_a_id
            m_b, l_b, k_b = node_b_id

            # 3. P値が同じかどうかチェック
            p_val_a = self.p_value_maps[m_a].get((l_a, k_a))
            p_val_b = self.p_value_maps[m_b].get((l_b, k_b))

            if p_val_a is None or p_val_a != p_val_b:
                continue # P値が異なるか、取得できなければスキップ

            # 4. 2つともリーフノード(試薬のみで構成されるノード)の場合は除外
            # (同じ試薬を混ぜるピアノードは無意味なため)
            f_a = self.targets_config[m_a]["factors"][l_a]
            f_b = self.targets_config[m_b]["factors"][l_b]
            is_leaf_a = p_val_a == f_a
            is_leaf_b = p_val_b == f_b
            if is_leaf_a and is_leaf_b:
                continue

            # 5. ピア(R)ノードを定義
            name = f"peer_mixer_t{m_a}l{l_a}k{k_a}-t{m_b}l{l_b}k{k_b}"

            peer_node = {
                "name": name,
                "source_a_id": node_a_id, # 材料AのノードID
                "source_b_id": node_b_id, # 材料BのノードID
                "p_value": p_val_a,       # P値 (A, B と同じ)
                "ratio_vars": [ # ピア(R)ノード自身の比率変数
                    z3.Int(f"ratio_{name}_r{t}") for t in range(self.num_reagents)
                ],
                "input_vars": { # ピア(R)ノードへの入力変数
                    "from_a": z3.Int(f"share_peer_a_to_{name}"),
                    "from_b": z3.Int(f"share_peer_b_to_{name}"),
                },
            }
            peer_nodes.append(peer_node)

        print(f"  -> Found {len(peer_nodes)} potential peer-mixing combinations.")
        return peer_nodes

    def _precompute_potential_sources_v2(self):
        """
        各DFMMノード（供給先）が、どのノード（供給元）から中間液を受け取れる
        可能性があるかを、制約に基づいて事前に計算する。
        
        これにより、ソルバーが考慮すべき共有変数の数を大幅に削減できる。
        
        Returns:
            dict: source_map[供給先ノードID] = [供給元ノードIDのリスト]
        """
        source_map = {}
        
        # 1. 全ての「供給先」ノード (DFMMノード) のリスト
        all_dest_nodes = [
            (target_idx, level, node_idx)
            for target_idx, tree in enumerate(self.forest)
            for level, nodes in tree.items()
            for node_idx in range(len(nodes))
        ]
        
        # 2. 全ての「供給元」ノード (DFMMノード + ピア(R)ノード) のリスト
        all_dfmm_sources = list(all_dest_nodes)
        # ピア(R)ノードは (target_idx, level, node_idx) のタプルで表現
        # ( "R", (ピアのインデックス), 0 (ダミー) )
        all_peer_sources = [("R", i, 0) for i in range(len(self.peer_nodes))]
        all_sources = all_dfmm_sources + all_peer_sources

        # 3. 全ての (供給先, 供給元) の組み合わせを総当たり
        for (
            (dst_target_idx, dst_level, dst_node_idx), # 供給先 (Destination)
            (src_target_idx, src_level, src_node_idx), # 供給元 (Source)
        ) in itertools.product(all_dest_nodes, all_sources):
            
            # --- 供給先(dst)のP値とFactorを取得 ---
            p_dst = self.p_value_maps[dst_target_idx][(dst_level, dst_node_idx)]
            f_dst = self.targets_config[dst_target_idx]["factors"][dst_level]

            # --- 供給元(src)のP値と実効レベル(l_src_eff)を取得 ---
            if src_target_idx == "R":
                # 供給元がピア(R)ノードの場合
                peer_node = self.peer_nodes[src_level] # src_level はピアのインデックス
                p_src = peer_node["p_value"]
                # ピア(R)ノードの実効レベルは、その材料(A, B)のレベルの高い方
                l_src_eff = max(
                    peer_node["source_a_id"][1], peer_node["source_b_id"][1]
                )
            else:
                # 供給元がDFMMノードの場合
                p_src = self.p_value_maps[src_target_idx][(src_level, src_node_idx)]
                l_src_eff = src_level
                # 自分自身への供給は不可
                if (dst_target_idx, dst_level, dst_node_idx) == (
                    src_target_idx,
                    src_level,
                    src_node_idx,
                ):
                    continue

            # --- 4. 接続可能性のチェック ---

            # [制約1: レベル]
            # 供給元は、供給先より「下位」のレベル (level値が大きい) になければならない
            # (ただし、rootノード (l_src_eff == 0) はどこにでも供給できる)
            is_valid_level_connection = (l_src_eff > dst_level) or (l_src_eff == 0)
            if not is_valid_level_connection:
                continue
                
            # [制約2: 最大レベル差] (config.py の設定)
            if MAX_LEVEL_DIFF is not None and l_src_eff > dst_level + MAX_LEVEL_DIFF:
                continue

            # [制約3: P値の互換性] (最も重要)
            # 供給先の「基本単位」 (p_dst // f_dst) は、
            # 供給元の「P値」 (p_src) で割り切れなければならない
            # (例: p_dst=18, f_dst=3 -> 基本単位=6。 p_src=2 -> 6%2==0 OK)
            # (例: p_dst=18, f_dst=3 -> 基本単位=6。 p_src=4 -> 6%4!=0 NG)
            if (p_dst // f_dst) % p_src != 0:
                continue

            # --- 5. 接続可能と判断 ---
            key = (dst_target_idx, dst_level, dst_node_idx)
            if key not in source_map:
                source_map[key] = []
            # 供給先ノードをキーとして、供給元ノードのリストに追加
            source_map[key].append((src_target_idx, src_level, src_node_idx))
            
        return source_map

    def _create_sharing_vars_for_node(self, dst_target_idx, dst_level, dst_node_idx):
        """
        特定の「供給先」ノードに対して、
        `_precompute_potential_sources_v2` で見つかった「供給元」からの
        共有液量を表すz3変数（w_intra, w_inter）の辞書を作成します。
        """
        # 事前計算マップから、この供給先ノードに接続可能な供給元リストを取得
        potential_sources = self.potential_sources_map.get(
            (dst_target_idx, dst_level, dst_node_idx), []
        )
        intra_vars, inter_vars = {}, {} # ツリー内 / ツリー間

        for src_target_idx, src_level, src_node_idx in potential_sources:
            if src_target_idx == dst_target_idx:
                # (A) ツリー内 (Intra) 共有
                key_str = create_intra_key(src_level, src_node_idx) # 例: "l1k0"
                key = f"from_{key_str}" # 例: "from_l1k0"
                name = (
                    f"share_intra_t{dst_target_idx}_from_{key_str}"
                    f"_to_l{dst_level}k{dst_node_idx}"
                )
                intra_vars[key] = z3.Int(name)
            else:
                if src_target_idx == "R":
                    # (B) ピア(R)ノード (Inter) 共有
                    key_str = create_peer_key(src_level)  # src_levelはRノードのindex (例: "R_idx0")
                    key = f"from_{key_str}" # 例: "from_R_idx0"
                    name = (
                        f"share_inter_from_{key_str}"
                        f"_to_t{dst_target_idx}l{dst_level}k{dst_node_idx}"
                    )
                    inter_vars[key] = z3.Int(name)
                else:
                    # (C) ツリー間 (Inter) DFMMノード共有
                    key_str = create_inter_key(src_target_idx, src_level, src_node_idx) # 例: "t1_l1k0"
                    key = f"from_{key_str}" # 例: "from_t1_l1k0"
                    name = (
                        f"share_inter_from_{key_str}"
                        f"_to_t{dst_target_idx}l{dst_level}k{dst_node_idx}"
                    )
                    inter_vars[key] = z3.Int(name)
        return intra_vars, inter_vars

    def _define_sharing_variables(self):
        """
        全てのDFMMノードをループし、_create_sharing_vars_for_node を呼び出して、
        共有変数を `self.forest` の各ノード辞書に格納します。
        """
        for dst_target_idx, tree_dst in enumerate(self.forest):
            for dst_level, nodes_dst in tree_dst.items():
                for dst_node_idx, node in enumerate(nodes_dst):
                    # 各ノード (供給先) ごとに共有変数を生成
                    intra, inter = self._create_sharing_vars_for_node(
                        dst_target_idx, dst_level, dst_node_idx
                    )
                    # ノードの辞書に 'intra_sharing_vars' と 'inter_sharing_vars' を追加
                    node["intra_sharing_vars"] = intra
                    node["inter_sharing_vars"] = inter