# Beta Bundles

Example of monitoring L2 auction for winning bids, then submitting bundles.

## Installation

1. **Clone the Repository:**
    ```bash
    git clone <repository_url>
    ```

2. **Install Poetry:**
    ```bash
    curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | python3
    ```

3. **Install Dependencies:**
    ```bash
    poetry install
    ```

## Configuration

Before running the script, ensure to set up the following environment variables:

- `L2_RPC`: RPC endpoint for connecting to Layer 2.
- `BETA_BUNDLE_RPC`: RPC endpoint for submitting beta bundles.
- `AUCTIONEER`: Address of the auctioneer contract.
- `SETTLEMENT`: Address of the settlement contract.
- `BIDDER`: Address of the bidder contract.
- `CALLER`: Ethereum address of the caller.
- `PRIVATE_KEY`: Private key associated with the caller's address.

## Usage
```bash
poetry run beta_bundles_py/main.py
```

## Features

- **Event Handling:** Monitors Ethereum events for auction settlements.
- **Bundle Submission:** Submits bundles upon detecting settled auctions.
- **Transaction Signing:** Signs transactions using the provided private key.

## Contributing

Contributions are welcome! If you find any issues or have suggestions for improvements, feel free to open an issue or submit a pull request.

## License

This project is licensed under the [MIT License](LICENSE).
