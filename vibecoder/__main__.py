"""Allow running as python -m vibecoder."""

# Suppress google-generativeai deprecation warnings before any imports trigger them
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning, module="google")

from .main import main

if __name__ == "__main__":
    main()
