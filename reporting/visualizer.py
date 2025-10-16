# reporting/visualizer.py
import os
import networkx as nx
import matplotlib.pyplot as plt
import z3
import matplotlib.colors as mcolors

class SolutionVisualizer:
    """
    最適化された混合手順（ソルバーの解）を、networkxとmatplotlibを用いて
    有向グラフとして可視化し、画像ファイルとして保存するクラス。
    """

    # グラフの見た目を定義する設定
    STYLE_CONFIG = {
        'mix_node': {'color': '#87CEEB', 'size': 2000},       # 中間生成物ノード
        'target_node': {'color': '#90EE90', 'size': 2000},    # 最終ターゲットノード
        'reagent_node': {'color': '#FFDAB9', 'size': 1500},   # 試薬ノード
        'waste_node': {'color': 'black', 'size': 300, 'shape': 'o'}, # 廃棄物ノード
        'default_node': {'color': 'gray', 'size': 1000},
        'edge': {'width': 1.5, 'arrowsize': 20, 'connectionstyle': 'arc3,rad=0.1'}, # 矢印（エッジ）
        'font': {'font_size': 10, 'font_weight': 'bold', 'font_color': 'black'}, # ラベルフォント
        'edge_label_bbox': dict(facecolor='white', edgecolor='none', alpha=0.7, pad=1), # エッジラベルの背景
        'edge_colormap': 'viridis', # エッジの重み付けに使用するカラーマップ
    }
    # ノードの配置に関する設定
    LAYOUT_CONFIG = {
        'x_gap': 6.0, 'y_gap': 5.0, 'tree_gap': 10.0, # ノード間・ツリー間のギャップ
        'waste_node_offset_x': 3.5, 'waste_node_stagger_y': 0.8, # 廃棄ノードのオフセット
    }

    def __init__(self, problem, model):
        """
        コンストラクタ。

        Args:
            problem (MTWMProblem): 最適化問題の定義オブジェクト。
            model (z3.ModelRef): Z3ソルバーが見つけた解のモデル。
        """
        self.problem = problem
        self.model = model

    def visualize_solution(self, output_dir):
        """
        混合ツリーのグラフを構築し、画像として保存するメインメソッド。
        """
        # モデルからグラフデータを構築
        graph, edge_volumes = self._build_graph_from_model()
        if not graph.nodes():
            print("No active nodes to visualize.")
            return

        # ノードの配置座標を計算
        positions = self._calculate_node_positions(graph)
        # グラフを描画して保存
        self._draw_graph(graph, positions, edge_volumes, output_dir)

    def _build_graph_from_model(self):
        """
        Z3ソルバーのモデルを解析し、networkx用のグラフデータ（ノードとエッジ）を構築します。
        """
        G = nx.DiGraph()
        edge_volumes = {} # エッジに表示する液量を保存する辞書

        # アクティブな（実際に使われている）ノードのみを処理
        for m, l, k, node, total_input in self._iterate_active_nodes():
            node_name = f"m{m}_l{l}_k{k}"
            ratio_vals = [self.model.eval(r).as_long() for r in node['ratio_vars']]
            # ノードに表示するラベルを生成 (ルートノードは特別扱い)
            label = f"R{m+1}:[{':'.join(map(str, ratio_vals))}]" if l == 0 else ':'.join(map(str, ratio_vals))

            # グラフにノードを追加。描画に必要な情報を属性として持たせる
            G.add_node(node_name, label=label, level=l, target=m, type='mix')

            # 廃棄、試薬、共有の各要素をグラフに追加
            self._add_waste_node(G, node, node_name)
            self._add_reagent_edges(G, edge_volumes, node, node_name, l, m)
            self._add_sharing_edges(G, edge_volumes, node, node_name, m)

        return G, edge_volumes

    def _iterate_active_nodes(self):
        """モデルで実際に使用されている（総入力が0より大きい）ノードのみを巡回するジェネレータ。"""
        for m, tree in enumerate(self.problem.forest):
            for l, nodes in tree.items():
                for k, node in enumerate(nodes):
                    inputs = (node.get('reagent_vars', []) +
                              list(node.get('intra_sharing_vars', {}).values()) +
                              list(node.get('inter_sharing_vars', {}).values()))
                    total_input = self.model.eval(z3.Sum(inputs)).as_long()
                    if total_input > 0:
                        yield m, l, k, node, total_input

    def _add_waste_node(self, G, node, parent_name):
        """ノードに廃棄物があれば、グラフに廃棄ノード（黒点）と非表示エッジを追加する。"""
        waste_var = node.get('waste_var')
        if waste_var is not None and self.model.eval(waste_var).as_long() > 0:
            waste_node_name = f"waste_{parent_name}"
            G.add_node(waste_node_name, level=G.nodes[parent_name]['level'], target=G.nodes[parent_name]['target'], type='waste')
            # 廃棄ノードを親の右に配置するための非表示エッジ
            G.add_edge(parent_name, waste_node_name, style='invisible')

    def _add_reagent_edges(self, G, edge_volumes, node, dest_name, level, target_idx):
        """試薬から混合ノードへのエッジ（矢印）を追加する。"""
        for r_idx, r_var in enumerate(node.get('reagent_vars', [])):
            if (r_val := self.model.eval(r_var).as_long()) > 0:
                reagent_name = f"Reagent_{dest_name}_t{r_idx}"
                # 試薬ノードを追加（①, ②, ...）
                G.add_node(reagent_name, label=chr(0x2460 + r_idx), level=level + 1, target=target_idx, type='reagent')
                G.add_edge(reagent_name, dest_name, volume=r_val)
                edge_volumes[(reagent_name, dest_name)] = r_val

    def _add_sharing_edges(self, G, edge_volumes, node, dest_name, dest_tree_idx):
        """中間液の共有（あるノードから別のノードへの液体の流れ）を表すエッジを追加する。"""
        all_sharing = {**node.get('intra_sharing_vars',{}), **node.get('inter_sharing_vars',{})}
        for key, w_var in all_sharing.items():
            if (val := self.model.eval(w_var).as_long()) > 0:
                src_name = self._parse_source_node_name(key, dest_tree_idx)
                G.add_edge(src_name, dest_name, volume=val)
                edge_volumes[(src_name, dest_name)] = val

    def _parse_source_node_name(self, key, dest_tree_idx):
        """共有変数のキー文字列（'from_m0_l2k1'など）から供給元ノード名を復元する。"""
        key = key.replace('from_', '')
        if key.startswith('m'): # inter-sharing (ツリー間)
            m_src, lk_src = key.split('_l')
            l_src, k_src = lk_src.split('k')
            return f"{m_src}_l{l_src}_k{k_src}"
        else: # intra-sharing (ツリー内)
            l_src, k_src = key.split('k')
            return f"m{dest_tree_idx}_l{l_src.replace('l','')}_k{k_src}"

    def _calculate_node_positions(self, G):
        """ノードを見やすく配置するための座標（x, y）を計算する。"""
        pos = {}
        # ターゲットごとにX座標をずらして配置
        targets = sorted({d["target"] for n, d in G.nodes(data=True) if d.get("target") is not None})
        current_x_offset = 0.0

        for target_idx in targets:
            sub_nodes = [n for n, d in G.nodes(data=True) if d.get("target") == target_idx and d.get("type") != "waste"]
            if not sub_nodes: continue

            max_width = self._position_nodes_by_level(G, pos, sub_nodes, current_x_offset)
            self._position_waste_nodes(G, pos, target_idx)
            current_x_offset += max_width + self.LAYOUT_CONFIG['tree_gap']

        return pos

    def _position_nodes_by_level(self, G, pos, sub_nodes, x_offset):
        """同じターゲット内で、レベル（階層）ごとにノードのX,Y座標を決定する。"""
        max_width_in_tree = 0
        levels = sorted({G.nodes[n]["level"] for n in sub_nodes})

        for level in levels:
            nodes_at_level = [n for n in sub_nodes if G.nodes[n].get("level") == level]
            # 試薬ノードも同じレベルに並べる
            reagent_nodes = {u for n in nodes_at_level for u, _ in G.in_edges(n) if G.nodes.get(u, {}).get("type") == "reagent"}
            full_row = sorted(list(set(nodes_at_level) | reagent_nodes))

            # レベル内のノードを中央揃えで均等に配置
            total_width = (len(full_row) - 1) * self.LAYOUT_CONFIG['x_gap']
            start_x = x_offset - total_width / 2.0

            for i, node_name in enumerate(full_row):
                pos[node_name] = (start_x + i * self.LAYOUT_CONFIG['x_gap'], -level * self.LAYOUT_CONFIG['y_gap'])
            max_width_in_tree = max(max_width_in_tree, total_width)

        return max_width_in_tree

    def _position_waste_nodes(self, G, pos, target_idx):
        """廃棄ノードを、対応する親ノードの右側に配置する。"""
        waste_nodes = [n for n, d in G.nodes(data=True) if d.get("type") == "waste" and d.get("target") == target_idx]
        for wn in waste_nodes:
            parent = next(iter(G.predecessors(wn)), None)
            if parent and parent in pos:
                px, py = pos[parent]
                pos[wn] = (px + self.LAYOUT_CONFIG['waste_node_offset_x'], py)

    def _draw_graph(self, G, pos, edge_volumes, output_dir):
        """計算された座標に基づき、matplotlibでグラフを描画しPNGファイルとして保存する。"""
        fig, ax = plt.subplots(figsize=(20, 12))

        drawable_nodes = [n for n in G.nodes() if n in pos]
        drawable_edges = [(u, v) for u, v, d in G.edges(data=True) if d.get('style') != 'invisible' and u in pos and v in pos]

        node_styles = {n: self._get_node_style(G.nodes[n]) for n in drawable_nodes}

        # ノードの形状ごとに描画（matplotlibの仕様）
        for shape in {s['shape'] for s in node_styles.values()}:
            nodelist = [n for n, s in node_styles.items() if s['shape'] == shape]
            nx.draw_networkx_nodes(G, pos, ax=ax, nodelist=nodelist, node_shape=shape,
                                   node_size=[node_styles[n]['size'] for n in nodelist],
                                   node_color=[node_styles[n]['color'] for n in nodelist],
                                   edgecolors='black', linewidths=1.0)

        # ラベル、エッジ、エッジラベルを描画
        labels = {n: d['label'] for n, d in G.nodes(data=True) if n in drawable_nodes and 'label' in d and d.get('type') != 'waste'}
        nx.draw_networkx_labels(G, pos, ax=ax, labels=labels, **self.STYLE_CONFIG['font'])
        
        # エッジの重みに基づいて色を決定
        if edge_volumes:
            volumes = [edge_volumes[edge] for edge in drawable_edges]
            if volumes:
                min_vol = min(volumes)
                max_vol = max(volumes)
                
                # 正規化関数
                norm = mcolors.Normalize(vmin=min_vol, vmax=max_vol)
                # カラーマップの取得
                cmap = plt.get_cmap(self.STYLE_CONFIG['edge_colormap'])
                
                edge_colors = [cmap(norm(edge_volumes[edge])) for edge in drawable_edges]
            else:
                edge_colors = ['gray'] * len(drawable_edges) # エッジがない場合はデフォルト色
        else:
            edge_colors = ['gray'] * len(drawable_edges) # edge_volumesが空の場合

        nx.draw_networkx_edges(G, pos, edgelist=drawable_edges, ax=ax, node_size=self.STYLE_CONFIG['mix_node']['size'],
                               edge_color=edge_colors, # ここで色を指定
                               **self.STYLE_CONFIG['edge'])

        edge_labels = {k: v for k, v in edge_volumes.items() if k in drawable_edges}
        nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels,
                                     font_size=self.STYLE_CONFIG['font']['font_size'],
                                     font_color=self.STYLE_CONFIG['font']['font_color'],
                                     bbox=self.STYLE_CONFIG['edge_label_bbox'])

        # カラーバーの追加（オプション）
        if edge_volumes and volumes:
            sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
            sm.set_array([])
            cbar = fig.colorbar(sm, ax=ax, orientation='vertical', fraction=0.02, pad=0.04)
            cbar.set_label("Volume", rotation=270, labelpad=15, fontsize=12)


        ax.set_title("Mixing Tree Visualization", fontsize=18, pad=20)
        ax.axis('off')
        plt.tight_layout()
        image_path = os.path.join(output_dir, 'mixing_tree_visualization.png')

        try:
            plt.savefig(image_path, dpi=300, bbox_inches='tight')
            print(f"Graph visualization saved to: {image_path}")
        except Exception as e:
            print(f"Error saving visualization image: {e}")
        finally:
            plt.close(fig)

    def _get_node_style(self, node_data):
        """ノードのデータ（typeなど）に基づいて、適用するスタイル辞書を返すヘルパー関数。"""
        cfg = self.STYLE_CONFIG
        node_type = node_data.get('type')
        if node_type == 'mix': style = cfg['target_node'] if node_data.get('level') == 0 else cfg['mix_node']
        elif node_type == 'reagent': style = cfg['reagent_node']
        elif node_type == 'waste': style = cfg['waste_node']
        else: style = cfg['default_node']
        return {'color': style['color'], 'size': style['size'], 'shape': style.get('shape', 'o')}