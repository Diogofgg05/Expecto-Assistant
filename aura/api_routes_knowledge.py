"""Knowledge quality, evidence and read-only learning routes."""
from __future__ import annotations
from fastapi import HTTPException


def register_knowledge_routes(app, engine, db):
    @app.get('/api/optimizer/status')
    async def optimizer_status():
        # Read-only summary, no training from HTTP requests.
        return engine.optimizer.status()

    @app.get('/api/learning/status')
    async def learning_status():
        return {'enabled':db.get_option('advanced_learning_enabled','false')=='true',
                **engine.learning.stats()}

    @app.get('/api/learning/claims')
    async def learning_claims(topic: str = '', limit: int = 25):
        return {'items':engine.learning.claims(topic[:160],min(max(limit,1),50))}

    @app.get('/api/epistemics/claims/{claim_id}')
    async def epistemic_claim(claim_id: str):
        try: result=engine.epistemics.assess(claim_id)
        except ValueError: raise HTTPException(status_code=422,detail='ID inválido.')
        if result is None: raise HTTPException(status_code=404,detail='Hipótese desconhecida.')
        return result

    @app.get('/api/epistemics/audits')
    async def epistemic_audits(limit: int = 20):
        return {'items':engine.epistemics.latest(min(100,max(1,limit)))}

    @app.get('/api/quality/claims/{claim_id}')
    async def quality_claim(claim_id: str):
        try: result=engine.quality.inspect(claim_id)
        except ValueError: raise HTTPException(status_code=422,detail='ID inválido.')
        if result is None: raise HTTPException(status_code=404,detail='Hipótese desconhecida.')
        return result

    @app.get('/api/factcheck/history')
    async def factual_history(limit: int = 20):
        return {'items':engine.factcheck.latest(limit)}

    @app.get('/api/factcheck/claims/{claim_id}')
    async def factual_claim(claim_id: str):
        try: result=engine.factcheck.offline(claim_id)
        except ValueError: raise HTTPException(status_code=422,detail='ID inválido.')
        if result is None: raise HTTPException(status_code=404,detail='Hipótese desconhecida.')
        return result

    @app.get('/api/quality/summary')
    async def quality_summary(limit: int = 25):
        return engine.quality.overview(limit)

