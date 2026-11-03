import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;

/**
 * Trace SSC's frequency-dependent headroom and band allocation functions.
 * Only use with a private, locally extracted libScalable_Encoder.so.
 *
 * Decompiler output is proprietary vendor pseudocode and must NOT be
 * uploaded to the research Git repository.
 */
public class TraceSscHeadroom extends GhidraScript {
    public void run() throws Exception {
        String[] targets = {
            "ssc_encode",
            "normal_headroom",
            "uhq_headroom",
            "ssc_compute_band_energies_for_lastband",
            "ssc_compute_allocation",
            "ssc_quant_all_bands"
        };
        DecompInterface d = new DecompInterface();
        d.openProgram(currentProgram);
        int count = 0;
        for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
            if (f.isThunk()) continue;
            for (String name : targets) {
                if (!name.equals(f.getName())) continue;
                println("\n### FUNCTION " + name + " @ " + f.getEntryPoint());
                DecompileResults r = d.decompileFunction(f, 90, monitor);
                if (r != null && r.decompileCompleted() && r.getDecompiledFunction() != null) {
                    String c = r.getDecompiledFunction().getC();
                    println("FUNCTION_SIZE_CHARS " + c.length());
                    println(c.substring(0, Math.min(c.length(), 15000)));
                } else {
                    println("DECOMPILATION_FAILED " + name);
                }
                count++;
                break;
            }
        }
        d.dispose();
        println("TOTAL_FUNCTIONS " + count);
    }
}
