// Disable the slowest analyzers before auto-analysis. Disassembly and references stay on.
// @category Research
import ghidra.app.script.GhidraScript;

public class PrepAnalysis extends GhidraScript {
    public void run() throws Exception {
        String[] off = {
            "Decompiler Parameter ID",
            "Function ID",
            "Shared Return Calls",
            "Condense Filler Bytes"
        };
        for (String name : off) {
            try {
                setAnalysisOption(currentProgram, name, "false");
                println("disabled " + name);
            } catch (Exception e) {
                println("option unavailable " + name);
            }
        }
    }
}
