from main import main


def test_main_runs(capsys: object) -> None:
    main()
    captured = capsys.readouterr()
    assert "nm-ai2" in captured.out
