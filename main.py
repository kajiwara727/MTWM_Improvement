from runners import RUNNER_MAP
from utils.config_loader import Config


def main():
    """
    アプリケーションのエントリーポイント。
    config.py の MODE の値に基づき、
    RUNNER_MAPから適切な実行戦略（ランナー）を選択して処理を開始します。
    """
    mode = Config.MODE
    print(f"--- Factor Determination Mode: {mode.upper()} ---")

    # Now RUNNER_MAP is imported from runners
    runner_class = RUNNER_MAP.get(mode)

    if runner_class:
        runner = runner_class(Config)
        runner.run()
    else:
        raise ValueError(f"Unknown FACTOR_EXECUTION_MODE: '{mode}'.")


if __name__ == "__main__":
    main()
