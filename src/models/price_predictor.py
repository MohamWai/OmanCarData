class PricePredictorNotReady(NotImplementedError):
    pass


def predict_price(listing_features: dict) -> float:
    """Placeholder for future price prediction model."""
    raise PricePredictorNotReady(
        "Price prediction is deferred. The dashboard focuses on market exploration first."
    )
