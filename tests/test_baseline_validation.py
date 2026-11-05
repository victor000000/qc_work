from scripts.validate_strategies import baseline_specs


def test_sml01_baseline_writes_and_reads_only_the_owned_model_namespace():
    prefix = 'qcv/'+'a'*32+'/'
    specs = baseline_specs(prefix)
    assert [name for _,name,_,_ in specs] == ['baseline_s001','baseline_s002','baseline_sml01_train','baseline_sml01_infer']
    for _,name,main,extras in specs:
        if 'sml01' in name:
            assert prefix in main
            assert 'autoresearch/' not in main
            assert all('autoresearch/' not in code for code in extras.values())
