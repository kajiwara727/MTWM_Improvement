# utils/checkpoint.py
import pickle
import os
from .helpers import generate_config_hash

class CheckpointHandler:
    """
    計算の途中結果（チェックポイント）の保存と読み込みを管理するクラス。
    これにより、長時間の最適化計算が中断されても、見つかった最良の解から
    計算を再開することができます。
    """
    def __init__(self, targets_config, mode, run_name, config_hash):
        """
        コンストラクタ。

        Args:
            targets_config (list): 目標混合液の設定データ。
            mode (str): 最適化モード ('waste' or 'operations')。
            run_name (str): config.pyで設定された実行名。
            config_hash (str): この設定に一意なハッシュ値。
        """
        self.targets_config = targets_config
        self.mode = mode
        self.run_name = run_name
        self.config_hash = config_hash
        self.checkpoint_file = self._get_checkpoint_filename()

    def _get_checkpoint_filename(self):
        """
        設定ハッシュに基づき、一意のチェックポイントファイル名を生成します。
        例: "checkpoint_a1b2c3d4e5f6.pkl"
        """
        return f"checkpoint_{self.config_hash}.pkl"

    def save_checkpoint(self, analysis_results, best_value, elapsed_time):
        """
        現在の最適化状態（最良値、分析結果など）をpickleファイルに保存します。
        より良い解が見つかるたびに呼び出されます。

        Args:
            analysis_results (dict): reporterによって分析された現在の最良解の詳細。
            best_value (int): 現在の目的関数の最良値。
            elapsed_time (float): 計算開始からの経過時間。
        """
        print(f"Checkpoint saved to {self.checkpoint_file}. Current best {self.mode}: {best_value}")

        data_to_save = {
            'run_name': self.run_name,
            'targets_config': self.targets_config,
            'mode': self.mode,
            'analysis_results': analysis_results,
            'best_value': best_value,
            'elapsed_time': elapsed_time
        }

        # バイナリ書き込みモードでファイルを開き、データをダンプ
        with open(self.checkpoint_file, 'wb') as f:
            pickle.dump(data_to_save, f)

    def load_checkpoint(self):
        """
        チェックポイントファイルを読み込み、以前の計算状態を復元します。
        ファイルが存在しない、または破損している場合は、Noneを返して
        最初から計算を開始するように促します。

        Returns:
            tuple: (best_value, analysis_results) or (None, None)
        """
        if not os.path.exists(self.checkpoint_file):
            print("No checkpoint file found for this configuration. Starting fresh.")
            return None, None

        try:
            # バイナリ読み込みモードでファイルを開き、データをロード
            with open(self.checkpoint_file, 'rb') as f:
                data = pickle.load(f)

            # 念のため、現在の設定から計算したハッシュとファイル名が一致するか確認
            current_hash_check = generate_config_hash(self.targets_config, self.mode, self.run_name)
            if self.config_hash != current_hash_check:
                print("Warning: Checkpoint file is for a different configuration. Starting fresh.")
                return None, None

            print(f"Checkpoint loaded from {self.checkpoint_file}. Resuming with best {self.mode} < {data['best_value']}")
            return data['best_value'], data['analysis_results']

        except (EOFError, KeyError):
            # ファイルが空または不正な形式である場合の例外処理
            print("Warning: Checkpoint file is corrupted. Starting fresh.")
            self.delete_checkpoint()
            return None, None

    def delete_checkpoint(self):
        """
        現在の設定に対応する（破損した可能性のある）チェックポイントファイルを削除します。
        """
        if os.path.exists(self.checkpoint_file):
            os.remove(self.checkpoint_file)
            print(f"Removed checkpoint file: {self.checkpoint_file}")