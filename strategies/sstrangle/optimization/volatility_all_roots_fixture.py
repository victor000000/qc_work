"""Extend the verified native price-feature probe to all15 supported roots."""
from AlgorithmImports import Resolution,TradeBar,DataNormalizationMode
import json
from volatility_original_fixture import VolatilitySourceProbe

class AllRootsVolatilitySourceProbe(VolatilitySourceProbe):
    CONFIG = {}
    def initialize(self):
        super().initialize()
        roots=self.CONFIG['roots']
        if len(roots)!=15 or len(set(roots))!=15:raise RuntimeError('Full15root source scope required')
        self.canonicals={};self.symbol_to_root={};self.root_sids={}
        for root in roots:
            if root=='ZW':self.canonicals[root]=self.canonical
            else:
                canonical=self.add_future(root,Resolution.DAILY);canonical.set_filter(lambda u:u.contracts([]));self.canonicals[root]=canonical.symbol
        self.symbols=[]

    def probe(self):
        self.plot('Trading period','Equity',float(self.portfolio.total_portfolio_value))
        if not self.symbols:
            for root,canonical in self.canonicals.items():
                chain=sorted(self.futures_chain(canonical),key=lambda c:float(c.volume),reverse=True)
                selected=[c.symbol for c in chain[:2]]
                if len(selected)!=2 or len(set(str(s.id) for s in selected))!=2:raise RuntimeError('Two actual native deliveries unavailable:'+root)
                self.root_sids[root]=set(str(s.id) for s in selected)
                for symbol in selected:
                    self.add_future_contract(symbol,Resolution.DAILY);self.symbols.append(symbol);self.symbol_to_root[symbol]=root
        for symbol in self.symbols:
            sec=self.securities[symbol]
            if not sec.exchange.hours.is_date_open(sec.local_time):continue
            before=self.counts['aligned_windows']
            try:self.probe_symbol(symbol)
            except RuntimeError as error:
                # Calendar/source-label metadata only: never export prices,
                # volume, IV, or historical quote rows for diagnosis.
                last=list(self.history[TradeBar](symbol,2,Resolution.DAILY,fill_forward=False,data_normalization_mode=DataNormalizationMode.RAW))
                detail=dict(root=self.symbol_to_root[symbol],native_id=str(symbol.id),exchange_zone=str(sec.exchange.time_zone),local_decision=str(sec.local_time),expected_session=str(self.last_completed_session(sec.exchange.hours,sec.local_time)),source_last_start=str(last[-1].time) if last else None,source_last_end=str(last[-1].end_time) if last else None,source_rows=len(last),original_error=str(error))
                raise RuntimeError('Native daily calendar metadata '+json.dumps(detail,sort_keys=True)) from error
            if self.counts['aligned_windows']!=before+1:raise RuntimeError('Missing root source comparison')
            self.counts['root_'+self.symbol_to_root[symbol]]+=1

    def on_end_of_algorithm(self):
        if set(self.root_sids)!=set(self.CONFIG['roots']) or any(len(v)!=2 for v in self.root_sids.values()):raise RuntimeError('Incomplete native15root identities')
        if any(self.counts['root_'+root]<=0 for root in self.CONFIG['roots']):raise RuntimeError('A supported root lacks native feature proof')
        if sum(self.counts['root_'+root] for root in self.CONFIG['roots'])!=self.counts['requests']:raise RuntimeError('Root comparison counts do not reconcile')
        super().on_end_of_algorithm()
