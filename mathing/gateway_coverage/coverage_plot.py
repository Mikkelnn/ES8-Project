from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from coverage_calc import empirical_cdf, run_coverage_simulation


# ============================================================================
# Save helpers
# ============================================================================

PLOT_EXT = "svg"


def ensure_output_dir(path: str = "result") -> Path:
    """Create output folder if missing."""
    out_dir = Path(path)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def with_ext(filename_stem: str) -> str:
    """Return filename with configured plot extension."""
    return f"{filename_stem}.{PLOT_EXT}"


def save_figure(fig: plt.Figure, filepath: Path, close: bool = True) -> None:
    """Save a matplotlib figure and optionally close it."""
    fig.tight_layout()
    fig.savefig(filepath, bbox_inches="tight")
    if close:
        plt.close(fig)


def save_table_figure(
    rows: list[list[str]],
    col_labels: list[str],
    title: str,
    filepath: Path,
    figsize: tuple[float, float] = (10, 4),
    font_size: int = 10,
    scale: tuple[float, float] = (1.0, 1.3),
    cell_loc: str = "center",
) -> None:
    """Render and save a standalone table as an image."""
    fig, ax = plt.subplots(figsize=figsize)
    ax.axis("off")
    table = ax.table(
        cellText=rows,
        colLabels=col_labels,
        cellLoc=cell_loc,
        loc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(font_size)
    table.scale(*scale)
    ax.set_title(title, fontsize=12, fontweight="bold", pad=12)
    save_figure(fig, filepath)


# ============================================================================
# Plot helpers
# ============================================================================

def style_axes(
    ax: plt.Axes,
    title: str,
    xlabel: str,
    ylabel: str,
    xlim: tuple[float, float] | None = None,
) -> None:
    """Apply common axis styling."""
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(alpha=0.25)
    if xlim is not None:
        ax.set_xlim(*xlim)


def add_vertical_marker(ax: plt.Axes, x: float, label: str, color: str = "red") -> None:
    """Add a dashed vertical marker with legend label."""
    ax.axvline(
        x,
        linestyle="--",
        linewidth=2,
        color=color,
        zorder=5,
        label=label,
    )


def add_horizontal_marker(ax: plt.Axes, y: float, label: str, color: str = "red") -> None:
    """Add a dashed horizontal marker with legend label."""
    ax.axhline(
        y,
        linestyle="--",
        linewidth=2,
        color=color,
        zorder=5,
        label=label,
    )


def plot_empirical_cdf(
    samples: np.ndarray,
    title: str,
    xlabel: str,
    quantile_x: float | None = None,
    quantile_label: str | None = None,
) -> plt.Figure:
    """Create standalone empirical CDF plot."""
    x, cdf = empirical_cdf(samples)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(x, cdf, linewidth=2, zorder=2, label="CDF")
    if quantile_x is not None and quantile_label is not None:
        add_vertical_marker(ax, quantile_x, quantile_label, color="green")
    style_axes(ax, title, xlabel, "CDF")
    if quantile_x is not None:
        ax.legend()
    return fig


def plot_histogram(
    samples: np.ndarray,
    title: str,
    xlabel: str,
    mean_value: float | None = None,
    extra_vlines: list[tuple[float, str]] | None = None,
    bins: int = 60,
) -> plt.Figure:
    """Create standalone histogram plot."""
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(samples, bins=bins, density=True, alpha=0.75, edgecolor="black", zorder=2)
    if mean_value is not None:
        add_vertical_marker(ax, mean_value, f"Mean: {mean_value:.2f} dB", color="red")
    if extra_vlines:
        for x, label in extra_vlines:
            add_vertical_marker(ax, x, label, color="green")
    style_axes(ax, title, xlabel, "Probability Density")
    if mean_value is not None or extra_vlines:
        ax.legend()
    return fig


def plot_series_over_rounds(
    rounds_axis: np.ndarray,
    series: np.ndarray,
    title: str,
    ylabel: str,
    constant_level_db: float,
    series_label: str,
) -> plt.Figure:
    """Create standalone time-series plot over rounds with mean and constant markers."""
    fig, ax = plt.subplots(figsize=(11, 6))

    mean_value = float(np.mean(series))
    xlim = (float(np.min(rounds_axis)), float(np.max(rounds_axis)))

    ax.plot(rounds_axis, series, linewidth=1.0, label=series_label, zorder=2)
    add_horizontal_marker(ax, mean_value, f"Mean: {mean_value:.2f} dB", color="red")
    add_horizontal_marker(ax, constant_level_db, f"Constant part: {constant_level_db:.2f} dB", color="green")

    style_axes(ax, title, "Round", ylabel, xlim=xlim)
    ax.legend()
    return fig


def plot_cdf_on_axes(
    ax: plt.Axes,
    samples: np.ndarray,
    title: str,
    xlabel: str,
    quantile_x: float,
    quantile_label: str,
) -> None:
    """Draw a CDF plot on provided axes."""
    x, cdf = empirical_cdf(samples)
    ax.plot(x, cdf, linewidth=2, zorder=2, label="CDF")
    add_vertical_marker(ax, quantile_x, quantile_label, color="green")
    style_axes(ax, title, xlabel, "CDF")
    ax.legend(fontsize=8)


def plot_hist_on_axes(
    ax: plt.Axes,
    samples: np.ndarray,
    title: str,
    xlabel: str,
    mean_value: float,
    quantile_value: float,
    quantile_label: str,
    bins: int = 60,
) -> None:
    """Draw a histogram on provided axes."""
    ax.hist(samples, bins=bins, density=True, alpha=0.75, edgecolor="black", zorder=2)
    add_vertical_marker(ax, mean_value, f"Mean: {mean_value:.2f} dB", color="red")
    add_vertical_marker(ax, quantile_value, quantile_label, color="green")
    style_axes(ax, title, xlabel, "Probability Density")
    ax.legend(fontsize=8)


def plot_rounds_on_axes(
    ax: plt.Axes,
    rounds_axis: np.ndarray,
    series: np.ndarray,
    title: str,
    ylabel: str,
    constant_level_db: float,
    series_label: str,
) -> None:
    """Draw a rounds plot on provided axes."""
    mean_value = float(np.mean(series))
    xlim = (float(np.min(rounds_axis)), float(np.max(rounds_axis)))

    ax.plot(rounds_axis, series, linewidth=1.0, label=series_label, zorder=2)
    add_horizontal_marker(ax, mean_value, f"Mean: {mean_value:.2f} dB", color="red")
    add_horizontal_marker(ax, constant_level_db, f"Constant part: {constant_level_db:.2f} dB", color="green")
    style_axes(ax, title, "Round", ylabel, xlim=xlim)
    ax.legend(fontsize=8)


# ============================================================================
# Main plotting
# ============================================================================

def main() -> None:
    data = run_coverage_simulation()
    output_dir = ensure_output_dir("result_gateway_coverage")

    config = data["config"]
    samples = data["samples"]
    statistics = data["statistics"]
    surface_series = data["surface_series"]
    tables = data["tables"]

    rounds = config["rounds"]
    rounds_axis = np.arange(1, rounds + 1)
    tail_pct = (1.0 - config["reliability_target"]) * 100

    fading_samples = samples["fading_samples"]
    shadowing_samples = samples["shadowing_samples"]
    composite_samples = samples["composite_channel_gain_db"]

    fading_quantile = statistics["fading_quantile"]
    shadowing_quantile = statistics["shadowing_quantile"]
    composite_quantile = statistics["composite_quantile"]

    common_plot_specs = [
        (
            "fading_variation",
            fading_samples,
            "Fading Variation",
            "Fading variation (dB)",
            fading_quantile,
        ),
        (
            "shadowing_variation",
            shadowing_samples,
            "Shadowing Variation",
            "Shadowing variation (dB)",
            shadowing_quantile,
        ),
        (
            "composite_channel_variation",
            composite_samples,
            "Composite Channel Variation",
            "Composite channel variation (dB)",
            composite_quantile,
        ),
    ]

    # ------------------------------------------------------------------------
    # Save standalone tables
    # ------------------------------------------------------------------------
    table_specs = [
        (
            tables["info_rows"],
            ["Parameter", "Value"],
            "Simulation Parameters",
            "table_simulation_parameters",
            (10, 6.3),
            10,
            (1.05, 1.24),
            "left",
        ),
        (
            tables["budget_breakdown_rows"],
            [
                "Surface",
                "Base Constant Part (dB)",
                "Surface Loss (dB)",
                "Composite Margin (dB)",
                "Final Link Budget (dB)",
            ],
            "Link Budget Breakdown",
            "table_link_budget_breakdown",
            (12, 4.5),
            10,
            (1.0, 1.3),
            "center",
        ),
        (
            tables["results_rows"],
            [
                "Surface",
                "Environment",
                "n",
                "Link Budget (dB)",
                "Max Distance (m)",
            ],
            "LoRa Coverage Results",
            "table_coverage_results",
            (12, 6),
            9,
            (1.0, 1.25),
            "center",
        ),
    ]

    for rows, headers, title, stem, figsize, font_size, scale, cell_loc in table_specs:
        save_table_figure(
            rows=rows,
            col_labels=headers,
            title=title,
            filepath=output_dir / with_ext(stem),
            figsize=figsize,
            font_size=font_size,
            scale=scale,
            cell_loc=cell_loc,
        )

    # ------------------------------------------------------------------------
    # Save standalone common CDF and histogram plots
    # ------------------------------------------------------------------------
    for stem, sample_set, label_title, xlabel, quantile in common_plot_specs:
        quantile_label = f"{tail_pct:.4g}th pct: {quantile:.2f} dB"

        fig_cdf = plot_empirical_cdf(
            samples=sample_set,
            title=f"{label_title} Empirical CDF",
            xlabel=xlabel,
            quantile_x=quantile,
            quantile_label=quantile_label,
        )
        save_figure(fig_cdf, output_dir / with_ext(f"plot_{stem}_cdf"))

        fig_hist = plot_histogram(
            samples=sample_set,
            title=f"{label_title} Histogram",
            xlabel=xlabel,
            mean_value=float(np.mean(sample_set)),
            extra_vlines=[(quantile, quantile_label)],
        )
        save_figure(fig_hist, output_dir / with_ext(f"plot_{stem}_histogram"))

    # ------------------------------------------------------------------------
    # Save standalone rounds plots for all surfaces
    # ------------------------------------------------------------------------
    series_specs = [
        (
            "constant_plus_fading_series_db",
            "Constant Plus Fading Over Rounds",
            "Constant + fading",
            "plot_constant_plus_fading_over_rounds",
        ),
        (
            "constant_plus_shadowing_series_db",
            "Constant Plus Shadowing Over Rounds",
            "Constant + shadowing",
            "plot_constant_plus_shadowing_over_rounds",
        ),
        (
            "total_received_series_db",
            "Total Simulated Received-Power Variation Over Rounds",
            "Composite channel variation",
            "plot_total_received_power_over_rounds",
        ),
    ]

    for surface_name, series_data in surface_series.items():
        constant_received_level_db = series_data["constant_received_level_db"]
        surface_slug = surface_name.replace(" ", "_")

        for series_key, title_base, series_label, file_stem in series_specs:
            fig_series = plot_series_over_rounds(
                rounds_axis=rounds_axis,
                series=series_data[series_key],
                title=f"{title_base} ({surface_name})",
                ylabel="Level (dB)",
                constant_level_db=constant_received_level_db,
                series_label=series_label,
            )
            save_figure(
                fig_series,
                output_dir / with_ext(f"{file_stem}_{surface_slug}"),
            )

    # ------------------------------------------------------------------------
    # Combined plot collection
    # ------------------------------------------------------------------------
    dirt_keys = list(config["dirt_loss_db"].keys())
    n_rows = 6 + len(dirt_keys) * 3

    fig = plt.figure(figsize=(20, max(32, 3.3 * n_rows)))
    gs = fig.add_gridspec(
        n_rows,
        2,
        width_ratios=[1.15, 1.0],
        height_ratios=[1.0] * n_rows,
    )

    ax_info = fig.add_subplot(gs[0, 0])
    ax_budget = fig.add_subplot(gs[1, 0])
    ax_results = fig.add_subplot(gs[2:, 0])

    # Left side tables
    left_tables = [
        (
            ax_info,
            tables["info_rows"],
            ["Parameter", "Value"],
            "Simulation Parameters",
            10,
            (1.05, 1.18),
            "left",
        ),
        (
            ax_budget,
            tables["budget_breakdown_rows"],
            [
                "Surface",
                "Base Constant Part (dB)",
                "Surface Loss (dB)",
                "Composite Margin (dB)",
                "Final Link Budget (dB)",
            ],
            "Link Budget Breakdown",
            9.5,
            (1.0, 1.25),
            "center",
        ),
        (
            ax_results,
            tables["results_rows"],
            [
                "Surface",
                "Environment",
                "n",
                "Link Budget (dB)",
                "Max Distance (m)",
            ],
            "LoRa Coverage Results",
            9,
            (1.0, 1.18),
            "center",
        ),
    ]

    for ax, rows, headers, title, font_size, scale, cell_loc in left_tables:
        ax.axis("off")
        table = ax.table(
            cellText=rows,
            colLabels=headers,
            cellLoc=cell_loc,
            loc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(font_size)
        table.scale(*scale)
        ax.set_title(title, fontsize=12, fontweight="bold", pad=12)

    # Right side common plots
    common_axes = [
        fig.add_subplot(gs[0, 1]),
        fig.add_subplot(gs[1, 1]),
        fig.add_subplot(gs[2, 1]),
        fig.add_subplot(gs[3, 1]),
        fig.add_subplot(gs[4, 1]),
        fig.add_subplot(gs[5, 1]),
    ]

    for ax, (stem, sample_set, label_title, xlabel, quantile) in zip(common_axes[:3], common_plot_specs):
        plot_cdf_on_axes(
            ax=ax,
            samples=sample_set,
            title=f"{label_title} Empirical CDF",
            xlabel=xlabel,
            quantile_x=quantile,
            quantile_label=f"{tail_pct:.4g}th pct: {quantile:.2f} dB",
        )

    for ax, (stem, sample_set, label_title, xlabel, quantile) in zip(common_axes[3:], common_plot_specs):
        plot_hist_on_axes(
            ax=ax,
            samples=sample_set,
            title=f"{label_title} Histogram",
            xlabel=xlabel,
            mean_value=float(np.mean(sample_set)),
            quantile_value=quantile,
            quantile_label=f"{tail_pct:.4g}th pct: {quantile:.2f} dB",
        )

    # Surface-specific round plots
    start_row = 6
    for i, surface_name in enumerate(dirt_keys):
        row_base = start_row + i * 3
        series_data = surface_series[surface_name]
        constant_received_level_db = series_data["constant_received_level_db"]

        surface_round_specs = [
            (
                "constant_plus_fading_series_db",
                f"Constant Plus Fading Over Rounds ({surface_name})",
                "Constant + fading",
            ),
            (
                "constant_plus_shadowing_series_db",
                f"Constant Plus Shadowing Over Rounds ({surface_name})",
                "Constant + shadowing",
            ),
            (
                "total_received_series_db",
                f"Total Simulated Received-Power Variation Over Rounds ({surface_name})",
                "Composite channel variation",
            ),
        ]

        for j, (series_key, title, series_label) in enumerate(surface_round_specs):
            ax = fig.add_subplot(gs[row_base + j, 1])
            plot_rounds_on_axes(
                ax=ax,
                rounds_axis=rounds_axis,
                series=series_data[series_key],
                title=title,
                ylabel="Level (dB)",
                constant_level_db=constant_received_level_db,
                series_label=series_label,
            )

    save_figure(fig, output_dir / with_ext("plot_collection_summary"), close=False)

    print(f"Saved outputs to: {output_dir.resolve()}")
    print("Created files:")
    for path in sorted(output_dir.iterdir()):
        print(f" - {path.name}")

    plt.show()


if __name__ == "__main__":
    main()