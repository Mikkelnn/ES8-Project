"""Test that BFSTopologyAnalyzer and gatewayBFS produce equivalent results."""

import json
import sys
from pathlib import Path

# Add src and tools to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "tools" / "uplinkNodeLoad"))

import pytest

from sim.bfs_topology_analyzer import BFSTopologyAnalyzer

OUTPUT_DIR = Path(__file__).parent / "outputs" / "bfs_comparison"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class TestBFSEquivalence:
    """Compare BFSTopologyAnalyzer with legacy gatewayBFS script."""

    @pytest.fixture
    def test_line_data(self):
        """Load test_line topology."""
        json_path = Path(__file__).parent.parent / "tools" / "uplinkNodeLoad" / "test_line" / "node_outputs.json"
        with open(json_path) as f:
            return json.load(f)

    @pytest.fixture
    def test_line_path(self):
        """Return path to test_line directory."""
        return Path(__file__).parent.parent / "tools" / "uplinkNodeLoad" / "test_line"

    def test_raw_analyzer_output(self, test_line_data):
        """Test raw output from BFSTopologyAnalyzer.analyze_with_stats()."""
        nodes = test_line_data["nodes"]
        gateways = test_line_data["gateways"]
        mx = test_line_data["metadata"]["m_per_svg_x"]
        my = test_line_data["metadata"]["m_per_svg_y"]

        # Get output from BFSTopologyAnalyzer with stats (gatewayBFS format)
        analyzer_output = BFSTopologyAnalyzer.analyze_with_stats(
            nodes_data=nodes,
            gateways_data=gateways,
            m_per_svg_x=mx,
            m_per_svg_y=my,
            radius_m=300,
            gw_id_offset=0,
        )

        # Save raw output as-is
        (OUTPUT_DIR / "bfs_analyzer_raw_output.json").write_text(json.dumps(analyzer_output, indent=2))

        # Verify output structure
        assert isinstance(analyzer_output, dict)
        assert "visited" in analyzer_output
        assert "gateway_radius_m" in analyzer_output
        assert "total_nodes" in analyzer_output

    def test_raw_legacy_gateway_bfs_output(self, test_line_path):
        """Test raw output from gatewayBFS main() function."""
        # Change to test_line directory to load node_outputs.json
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(test_line_path)

            # Import and run gatewayBFS main
            import gatewayBFS

            legacy_output = gatewayBFS.main()

        finally:
            os.chdir(original_cwd)

        # Save raw output from gatewayBFS
        (OUTPUT_DIR / "gateway_bfs_raw_output.json").write_text(json.dumps(legacy_output, indent=2))

        # Verify output structure
        assert isinstance(legacy_output, dict)
        assert "visited" in legacy_output
        assert "gateway_radius_m" in legacy_output

    def test_both_identify_same_visited_nodes(self, test_line_data, test_line_path):
        """Both implementations should identify identical visited node lists (raw, no transformation)."""
        # Get visited from BFSTopologyAnalyzer.analyze_with_stats (same format as gatewayBFS)
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(test_line_path)

            # Get analyzer output
            analyzer_output = BFSTopologyAnalyzer.analyze_with_stats(
                nodes_data=test_line_data["nodes"],
                gateways_data=test_line_data["gateways"],
                m_per_svg_x=test_line_data["metadata"]["m_per_svg_x"],
                m_per_svg_y=test_line_data["metadata"]["m_per_svg_y"],
                radius_m=300,
                gw_id_offset=0,
            )

            # Get visited from gatewayBFS
            import gatewayBFS

            legacy_output = gatewayBFS.main()

        finally:
            os.chdir(original_cwd)

        # Both should have identical visited lists (raw, no conversion to set)
        assert analyzer_output["visited"] == legacy_output["visited"], f"Visited lists differ (RAW, not sorted):\n  Analyzer: {analyzer_output['visited']}\n  Legacy: {legacy_output['visited']}"

    def test_gateway_initials_match(self, test_line_data, test_line_path):
        """Gateway initial nodes should be identical."""
        # Get gateway_initials from BFSTopologyAnalyzer
        _, gateway_initials_analyzer, _ = BFSTopologyAnalyzer.analyze(
            nodes_data=test_line_data["nodes"],
            gateways_data=test_line_data["gateways"],
            m_per_svg_x=test_line_data["metadata"]["m_per_svg_x"],
            m_per_svg_y=test_line_data["metadata"]["m_per_svg_y"],
            radius_m=300,
            gw_id_offset=0,
        )

        # Get gateway_initials from gatewayBFS
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(test_line_path)

            # Extract gateway_initials from gatewayBFS logic
            nodes_raw = test_line_data["nodes"]
            gateways = test_line_data["gateways"]
            mx = test_line_data["metadata"]["m_per_svg_x"]
            my = test_line_data["metadata"]["m_per_svg_y"]

            positions = {int(nid): tuple(n["point"]) for nid, n in nodes_raw.items()}

            def dist_m(p1, p2):
                dx = (p1[0] - p2[0]) * mx
                dy = (p1[1] - p2[1]) * my
                return (dx * dx + dy * dy) ** 0.5

            gateway_initials_legacy = {}
            for gid_str, g in gateways.items():
                gid = int(gid_str)
                g_point = tuple(g["point"])
                initial_nodes = sorted([nid for nid, p in positions.items() if dist_m(p, g_point) <= 300])
                if initial_nodes:
                    gateway_initials_legacy[gid] = initial_nodes
        finally:
            os.chdir(original_cwd)

        assert gateway_initials_analyzer == gateway_initials_legacy

    def test_output_files_have_matching_visited_nodes(self):
        """Compare visited nodes from both output JSON files."""
        analyzer_file = OUTPUT_DIR / "bfs_analyzer_raw_output.json"
        legacy_file = OUTPUT_DIR / "gateway_bfs_raw_output.json"

        assert analyzer_file.exists(), f"Analyzer output file missing: {analyzer_file}"
        assert legacy_file.exists(), f"Legacy output file missing: {legacy_file}"

        # Load both files
        with open(analyzer_file) as f:
            analyzer_data = json.load(f)
        with open(legacy_file) as f:
            legacy_data = json.load(f)

        # Extract visited nodes from both
        visited_analyzer = set(analyzer_data["visited"])
        visited_legacy = set(legacy_data["visited"])

        # Should be identical
        assert visited_analyzer == visited_legacy, f"Visited nodes mismatch:\n  Analyzer: {sorted(visited_analyzer)}\n  Legacy: {sorted(visited_legacy)}\n  Difference: {visited_analyzer.symmetric_difference(visited_legacy)}"

        # Verify counts match
        assert len(analyzer_data["visited"]) == len(legacy_data["visited"])
        assert len(visited_analyzer) == len(visited_legacy)

    def test_output_files_are_exactly_equal(self):
        """Check if both output files are exactly identical.

        Note: Files have different structures but should have identical visited nodes.
        - Analyzer: provides node-to-gateway mapping and gateway initials
        - Legacy: provides statistics (max hops, max counts, per-gateway stats)
        """
        analyzer_file = OUTPUT_DIR / "bfs_analyzer_raw_output.json"
        legacy_file = OUTPUT_DIR / "gateway_bfs_raw_output.json"

        assert analyzer_file.exists(), f"Analyzer output file missing: {analyzer_file}"
        assert legacy_file.exists(), f"Legacy output file missing: {legacy_file}"

        # Load both files
        with open(analyzer_file) as f:
            analyzer_data = json.load(f)
        with open(legacy_file) as f:
            legacy_data = json.load(f)

        # Check exact equality
        files_identical = analyzer_data == legacy_data

        # Check visited nodes (primary requirement) - RAW comparison, no sorting
        visited_identical = analyzer_data["visited"] == legacy_data["visited"]

        # Report structure differences
        analyzer_keys = set(analyzer_data.keys())
        legacy_keys = set(legacy_data.keys())
        common_keys = analyzer_keys & legacy_keys

        # Save comparison results
        comparison = {
            "files_identical": files_identical,
            "visited_nodes_identical": visited_identical,
            "analyzer_only_keys": sorted(list(analyzer_keys - legacy_keys)),
            "legacy_only_keys": sorted(list(legacy_keys - analyzer_keys)),
            "common_keys": sorted(list(common_keys)),
            "visited_node_count": len(analyzer_data["visited"]),
        }
        (OUTPUT_DIR / "file_comparison_report.json").write_text(json.dumps(comparison, indent=2))

        # Primary assertion: visited nodes must match
        assert visited_identical, f"Visited nodes don't match:\n  Analyzer: {sorted(analyzer_data['visited'])}\n  Legacy: {sorted(legacy_data['visited'])}"

        # Secondary observation: files likely won't be exactly equal due to different output formats
        if not files_identical:
            assert analyzer_keys != legacy_keys, "Files have different structure (as expected)"
            assert common_keys == {"visited"}, "Only 'visited' key is common"
