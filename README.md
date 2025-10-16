# MTWM-Solver: 複数ターゲット混合における廃棄物最小化ソルバー 

### 概要

**MTWM (Multi-Target Waste Minimization) Solver**は、複数の目標混合液（Multi-Target）を生成する過程において、試薬の廃棄（Waste）を最小化（Minimization）する最適な手順を導き出すための高度な最適化計算ツールです。

***

### コアコンセプト

このソルバーは、主に2つの強力な理論に基づいています。

#### 1. DFMM (Digital Microfluidic Mixing) アルゴリズム
これは、目標とする混合比率を達成するために、どのような順序で、どのくらいの比率の液体を混ぜ合わせるべきか、という混合ツリーの「設計図」を自動生成するアルゴリズムです。

`core/dfmm.py`に実装されており、比率の合計値を素因数分解のように分割することで、多段階の混合プロセスを数学的に導出します。

#### 2. SMT (Satisfiability Modulo Theories) ソルバー
SMTソルバーは、複雑な制約条件を満たす解を見つけ出すことに特化した数学的な問題解決エンジンです。

本プロジェクトでは、業界で広く利用されている**Z3**を採用しています。

DFMMで生成された混合ツリーの無数の可能性の中から、「廃棄物量が最小になる」という条件を満たす唯一の解を、網羅的に探索する役割を担います。

***

### ファイル構成
```
MTWM_Solver_Refactored/
├── main.py                     # アプリケーションのエントリーポイント
├── config.py                   # 最適化の各種設定を行うファイル
├── z3_solver.py                # Z3ソルバーへの制約設定と最適化実行を担当
├── README.md                   # このファイル
|
├── core/                       # アプリケーションの中核ロジック
│   ├── __init__.py             # coreディレクトリをパッケージとして定義
│   ├── problem.py              # 最適化問題の構造を定義
│   └── dfmm.py                 # DFMMアルゴリズム関連
|
├── runners/                    # 実行モードごとの処理フローを管理
│   ├── __init__.py             # runnersディレクトリをパッケージとして定義
│   ├── base_runner.py          # 実行クラスの基底クラス
│   ├── standard_runner.py      # 'auto'/'manual'モード用
│   ├── random_runner.py        # 'random'モード用
│   └── permutation_runner.py   # 'auto_permutations'モード用
|
├── reporting/                  # 全ての出力・レポート関連機能
│   ├── __init__.py             # reportingディレクトリをパッケージとして定義
│   ├── analyzer.py             # 事前分析レポート
│   ├── reporter.py             # 詳細な結果レポート
│   ├── summary.py              # ランダム実行のサマリー
│   └── visualizer.py           # 結果の可視化
|
└── utils/                      # 汎用的な補助機能
    ├── __init__.py             # utilsディレクトリをパッケージとして定義
    ├── config_loader.py        # 設定の読み込み・解釈
    ├── checkpoint.py           # チェックポイント管理
    └── helpers.py              # ハッシュ生成などのヘルパー関数
``` 
### 機能詳細

#### 1. 廃棄物 & 操作回数の最適化
`config.py`の`OPTIMIZATION_MODE`で、何を最優先するかを選択できます。
* **`waste`モード**: 生成される総廃棄液量を最小化します。コスト削減や環境負荷低減に直結する最も基本的なモードです。
* **`operations`モード**: 混合操作の総回数を最小化します。操作時間がコストに大きく影響する場合や、プロセスの単純化を優先したい場合に有効です。

#### 2. 高度な共有ロジックによる廃棄物削減
異なるターゲット（例：製品Aと製品B）を製造する過程で偶然生まれた、仕様外の中間生成物があったとします。

このソルバーは、その中間生成物を別のターゲット（例：製品C）の製造に利用できないかを自動で探索します。

これにより、従来は廃棄されていた液体を再利用し、全体のコストと廃棄物を劇的に削減します。

#### 3. 包括的なレポートと可視化
最適化が完了すると、実行名に基づいたディレクトリ内に詳細なレポートが出力されます。
* **`summary.txt`**:
    * **最適化設定**: どの`MODE`で、どのような制約（ミキサー容量など）で計算したかの記録。
    * **最終結果**: 最小廃棄物量、総操作回数、総試薬使用量。
    * **混合プロセス詳細**: どのノード（`v_m0_l1_k0`など）で、どの試薬や中間液を、どれだけの量混合したか、という具体的な手順がすべて記録されます。
* **`mixing_tree_visualization.png`**:
    * **緑のノード**: 最終的に完成した目標混合液。
    * **水色のノード**: 中間生成物。
    * **オレンジのノード (①, ②..)**: 投入された純粋な試薬。
    * **矢印と数字**: 液体の流れと、その移動量を示します。
    * この図を見ることで、複雑な共有関係や混合プロセスを直感的に理解できます。

#### 4. 堅牢なチェックポイント機能
長時間の計算が中断されても進捗が失われないよう、堅牢なチェックポイント機能を備えています。
* **仕組み**: `config.py`の全設定（ターゲット比率、モード、制約など）から一意のハッシュ値を生成します。より良い解が見つかるたびに、このハッシュ値を含むファイル名（`checkpoint_xxxx.pkl`）で現在の最良解と計算状態が保存されます。
* **自動再開**: プログラムを再実行すると、まず現在の設定からハッシュ値を計算し、一致するチェックポイントファイルを探します。存在すれば、その時点の最良解を読み込み、それよりも良い解の探索から計算を再開するため、無駄な再計算が発生しません。

***

### アーキテクチャと処理フロー

本プログラムは、責務分離の原則に基づき、機能ごとにモジュール化されています。

1.  **起動 (`main.py`)**:
    * エントリーポイント。`config.py`の設定を`utils/config_loader.py`経由で読み込みます。
    * `FACTOR_EXECUTION_MODE`に応じて、`runners`パッケージから適切な実行戦略クラス（`StandardRunner`など）を選択し、インスタンス化します。

2.  **実行管理 (`runners/`)**:
    * 選択されたRunner（例: `RandomRunner`）が、シミュレーションのループや設定の生成など、全体の進行を管理します。
    * 個々の最適化タスクは、共通の`_run_single_optimization`メソッド（`base_runner.py`内）に渡されます。

3.  **問題構築 (`core/`)**:
    * `_run_single_optimization`内では、まず`core/dfmm.py`がターゲット設定から混合ツリーの構造を計算します。
    * 次に`core/problem.py`が、その構造に基づいてZ3ソルバーが扱うことのできる変数（液量、比率など）や関係性を定義します。

4.  **最適化 (`z3_solver.py`)**:
    * `core/problem`で定義された問題オブジェクトを受け取り、すべての制約（流量保存則、比率維持、物理的制約など）をZ3の形式に変換して追加します。
    * `opt.minimize()`を呼び出し、目的変数（総廃棄物量など）を最小化する解の探索を開始します。

5.  **出力 (`reporting/`)**:
    * Z3ソルバーが解を見つけると、`reporting/reporter.py`がそのモデルを解析し、人間が読める形式のサマリー（`summary.txt`）を生成します。
    * 同時に`reporting/visualizer.py`が混合フローのグラフを構築し、画像（`.png`）として保存します。

***

### 使い方ガイド：初めての最適化チュートリアル

このガイドでは、`manual`モードを使用して、特定のターゲット混合液の製造プロセスをゼロから最適化する手順を解説します。

---

#### ステップ1：環境のセットアップ

まず、プログラムを実行するための準備をします。

1.  **依存ライブラリのインストール**:
    ターミナル（コマンドプロンプト）を開き、以下のコマンドを実行して、必要なPythonライブラリをインストールします。

    ```bash
    pip install z3-solver networkx matplotlib
    ```

---

#### ステップ2：最適化シナリオの設定 (`config.py`)

次に、`config.py`ファイルを開き、どのような最適化を行いたいかを定義します。今回は、2種類のターゲット混合液（製品A, 製品B）の製造を想定します。

1.  **実行名の設定**:
    今回の実行結果が保存されるフォルダ名を決めます。

    ```python
    RUN_NAME = "My_First_Optimization"
    ```

2.  **実行モードの選択**:
    今回は、混合の階層（`factors`）を我々が直接指定する`manual`モードを使用します。

    ```python
    FACTOR_EXECUTION_MODE = "manual"
    ```
    * `auto`モード: `factors`を自動計算させたい場合。
    * `random`モード: ランダムな`ratios`で多数のシミュレーションを行いたい場合。
    * `auto_permutations`モード: `auto`で計算された`factors`の全順列を試し、最適な階層構造を探したい場合。

3.  **ターゲットの定義**:
    `TARGETS_FOR_MANUAL_MODE`のセクションを編集し、製造したい製品の仕様を定義します。

    ```python
    # --- 'manual' モード用設定 ---
    TARGETS_FOR_MANUAL_MODE = [
        # 製品A: 試薬1,2,3を [2:11:5] の比率で混合。合計18。
        # 混合階層(factors)は [3, 2, 3] とする。
        {'name': 'Product_A', 'ratios': [2, 11, 5], 'factors': [3, 2, 3]},

        # 製品B: 試薬1,2,3を [12:5:1] の比率で混合。合計18。
        # 混合階層(factors)は製品Aと同じ [3, 2, 3] を試す。
        {'name': 'Product_B', 'ratios': [12, 5, 1], 'factors': [3, 2, 3]},
    ]
    ```
    > **💡 `factors`とは？**
    > `ratios`の合計値（この例では18）を構成する因数です。これはDFMMアルゴリズムにおける混合の分割比を定義し、混合ツリーの構造を決定します。`[3, 2, 3]`は、3段階の混合プロセスを意味します。

---

#### ステップ3：最適化の実行

設定が完了したら、ターミナルで`main.py`を実行します。

```bash
python main.py
```

実行が始まると、ターミナルには以下のような進捗が表示されます。

- 設定内容の確認

- 事前分析レポートの保存先

- Z3ソルバーによる最適化の進捗（より良い解が見つかるたびに出力されます）

```
--- Factor Determination Mode: MANUAL ---
Using manually specified factors...

--- Configuration for this run ---
Run Name: My_First_Optimization
  - Product_A: Ratios = [2, 11, 5], Factors = [3, 2, 3]
  - Product_B: Ratios = [12, 5, 1], Factors = [3, 2, 3]
Optimization Mode: WASTE
-----------------------------------

All outputs for this run will be saved to: 'My_First_Optimization_xxxx/'
Pre-run analysis report saved to: My_First_Optimization_xxxx/_pre_run_analysis.txt
  Found new best solution: waste = 5
  Found new best solution: waste = 2
  ...
```

#### ステップ4：結果の分析と解釈
計算が完了すると、My_First_Optimization_xxxxという名前のディレクトリが生成されます。この中の2つの主要なファイルを見ていきましょう。

1. mixing_tree_visualization.png (可視化レポート)
まず、この画像を開いて全体像を把握します。

オレンジのノード (①, ②, ...): 外部から供給される純粋な試薬です。

水色のノード: 試薬や他の中間液を混ぜて作られた中間生成物です。

緑色のノード: 最終的に完成したターゲット製品（Product_A, Product_B）です。

矢印と数字: 液体の流れ（フロー）と、その移動量を示します。

黒い点: プロセス内で使用されず、最終的に廃棄される液量を示します。

2. summary.txt (詳細テキストレポート)
次に、テキストレポートで具体的な数値を確認します。

サマリーセクション:
```
========================================
Optimization Results for: My_First_Optimization_xxxx
========================================

Solved in 1.23 seconds.

--- Target Configuration ---
Target 1:
  Ratios: 2 : 11 : 5
  Factors: [3, 2, 3]
Target 2:
  Ratios: 12 : 5 : 1
  Factors: [3, 2, 3]

--- Optimization Settings ---
...
----------------------------

Minimum Total Waste: 2
Total mixing operations: 7
Total reagent units used: 38
```

ここで、総廃棄物が2ユニットで、合計7回の混合操作が必要だったことが分かります。

混合プロセス詳細セクション:
```
--- Mixing Process Details ---

[Target 1 (Product_A)]
 Level 1:
   Node v_m0_l1_k0: total_input = 6
     Ratio composition: [1, 5, 0]
     Mixing: 1 x Reagent1 + 5 x Reagent2
 Level 0:
   Node v_m0_l0_k0: total_input = 18
     Ratio composition: [2, 11, 5]
     Mixing: 1 x Reagent1 + 1 x Reagent3 + 1 x v_m1_l1_k0 + 5 x v_m0_l1_k0
```
このセクションは、可視化レポートの各ノードが「何でできているか」を示しています。

- ノード命名規則: v_m{ターゲット番号}_l{階層レベル}_k{ノードインデックス}

    - v_m0_l1_k0: ターゲット0番（Product_A）の、階層1（中間層）にある、0番目のノード。

- 解釈:

    - v_m0_l1_k0は、試薬1を1ユニット、試薬2を5ユニット混ぜて作られています。

    - 最終製品であるv_m0_l0_k0（Product_A）は、試薬1と3、そして中間液v_m0_l1_k0 だけでなく、ターゲット2の中間液であるv_m1_l1_k0も利用して作られていることが分かります。

このように、可視化レポートと詳細レポートを突き合わせることで、ソルバーがどのようにして廃棄物を削減する複雑な共有パスを発見したかを正確に理解することができます。
