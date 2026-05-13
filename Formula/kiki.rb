class Kiki < Formula
  desc "Persistent memory wiki for LLM coding assistants"
  homepage "https://github.com/plarotta/kiki"
  url "https://github.com/plarotta/kiki/archive/refs/tags/v0.1.3.tar.gz"
  sha256 "0e899a5f2f2ab6d061039c147d5c004bc6915c9c4eb86d0983c1578968d93638"
  license "MIT"
  head "https://github.com/plarotta/kiki.git", branch: "main"

  livecheck do
    url :stable
    strategy :github_latest
  end

  # External tools used at runtime (Claude Code, qmd, mcp Python pkg) are
  # intentionally not declared as deps — they're optional and handled by
  # `kiki init` / `kiki doctor` so users with their own toolchains aren't
  # forced into brew's versions. See caveats.

  def install
    bin.install "bin/kiki"
    bin.install "mcp/kiki-mcp.py" => "kiki-mcp"
    pkgshare.install "lib", "templates"
  end

  def caveats
    <<~EOS
      kiki integrates with several external tools that are not installed by Homebrew:

        - Claude Code  https://github.com/anthropics/claude-code
            Required for headless ingest/lint. Install separately.
        - qmd          https://github.com/tobi/qmd
            Hybrid search engine for the wiki. `kiki init` offers to install
            it for you (npm install -g @tobilu/qmd).
        - mcp (PyPI)   https://pypi.org/project/mcp/
            Required by the MCP server. Install with:
              pip3 install --user mcp

      First steps:
          kiki init
          kiki doctor

      Wiki data lives at ~/.kiki (override with $KIKI_HOME). `brew uninstall
      kiki` never touches it.
    EOS
  end

  test do
    # kiki resolves its prefix to HOMEBREW_PREFIX/share/kiki at test time
    assert_match version.to_s, shell_output("#{bin}/kiki version")
    assert_match "usage: kiki", shell_output("#{bin}/kiki help")

    ENV["KIKI_HOME"] = testpath/".kiki"
    assert_equal (testpath/".kiki").to_s, shell_output("#{bin}/kiki where").strip

    # capture writes a valid file even without a fully-initialized home,
    # as long as the dir exists and CLAUDE.md is present.
    (testpath/".kiki/raw/notes").mkpath
    (testpath/".kiki/CLAUDE.md").write("schema stub")
    output = pipe_output("#{bin}/kiki capture --type note --topic 'brew test' --signal 'verify'", "hello world")
    written = output.strip
    assert_path_exists Pathname.new(written)
    body = File.read(written)
    assert_match(/^type: note$/, body)
    assert_match(/^topic: "brew test"$/, body)
    assert_match(/hello world/, body)
  end
end
