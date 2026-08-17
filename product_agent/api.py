from fastapi import FastAPI
from product_agent.evaluation import evaluate_product_output
from product_agent.orchestrator import ProductIntelligenceOrchestrator
from product_agent.schemas import BatchRequest, ComponentStatus, EvaluationRequest, EvaluationScore, ProductInput, ProductIntelligence

app = FastAPI(title="Industrial Commerce Product AI Agent")
orchestrator = ProductIntelligenceOrchestrator()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/components", response_model=list[ComponentStatus])
def components() -> list[ComponentStatus]:
    return orchestrator.component_status()


@app.post("/process-product", response_model=ProductIntelligence)
def process_product(product: ProductInput) -> ProductIntelligence:
    return orchestrator.process_product(product)


@app.post("/batch", response_model=list[ProductIntelligence])
def batch(request: BatchRequest) -> list[ProductIntelligence]:
    return orchestrator.batch(request.products)


@app.get("/products", response_model=list[ProductIntelligence])
def products(limit: int = 50) -> list[ProductIntelligence]:
    return orchestrator.store.list_products(limit=limit)


@app.post("/evaluate", response_model=list[EvaluationScore])
def evaluate(request: EvaluationRequest) -> list[EvaluationScore]:
    return [
        EvaluationScore(key=score.key, score=score.score, comment=score.comment)
        for score in evaluate_product_output(request.product_input, request.output)
    ]
