from .cloud_evidence import published_order_count


def test_runtime_error_before_statistics_is_not_empty_tape():
    early={'completed':True,'error':'Margin Call','statistics':{},'progress':.489}
    assert published_order_count(early) is None
    final=dict(early,statistics={'Total Orders':'1,014'},progress=1)
    assert published_order_count(final)==1014


def test_explicit_empty_and_unfinished_publication():
    assert published_order_count({'completed':True,'statistics':{'Total Orders':'0'}})==0
    assert published_order_count({'completed':False,'statistics':{'Total Orders':'16'}}) is None
