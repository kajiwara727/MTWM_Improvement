# main.py
from config import FACTOR_EXECUTION_MODE
from runners import standard_runner, random_runner, permutation_runner
from utils.config_loader import Config

def main():
    """
    アプリケーションのエントリーポイント。
    設定ファイル (config.py) の FACTOR_EXECUTION_MODE の値に基づき、
    適切な実行戦略（ランナー）を選択して処理を開始します。
    """
    print(f"--- Factor Determination Mode: {FACTOR_EXECUTION_MODE.upper()} ---")

    # 設定モードに応じて適切なランナークラスをインスタンス化
    if FACTOR_EXECUTION_MODE in ['auto', 'manual']:
        # 'auto' または 'manual' モードの場合
        runner = standard_runner.StandardRunner(Config)
    elif FACTOR_EXECUTION_MODE == 'random':
        # 'random' モードの場合
        runner = random_runner.RandomRunner(Config)
    elif FACTOR_EXECUTION_MODE == 'auto_permutations':
        # 'auto_permutations' モードの場合
        runner = permutation_runner.PermutationRunner(Config)
    else:
        # 未知のモードが指定された場合はエラーを発生させる
        raise ValueError(f"Unknown FACTOR_EXECUTION_MODE: '{FACTOR_EXECUTION_MODE}'.")

    # 選択されたランナーの run() メソッドを実行して、処理を開始
    runner.run()

# このスクリプトが直接実行された場合に main() 関数を呼び出す
if __name__ == "__main__":
    main()