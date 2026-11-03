import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;

/** Private Ghidra analysis: how the encoder classifies and packages high rates. */
public class TraceSscRateModes extends GhidraScript {
    public void run() throws Exception {
        String[] names = {
            "get_uhq_info_from_bitrate", "set_data_frame_header",
            "set_data_header", "ssc_encoder_init", "ssc_hysteresis_decision",
            "set_limit_gain_from_bitrate", "get_header_from_bitrate"
        };
        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        int count = 0;
        for (Function f: currentProgram.getFunctionManager().getFunctions(true)) {
            if (f.isThunk()) continue;
            for (String name : names) {
                if (!f.getName().equals(name)) continue;
                DecompileResults results = decomp.decompileFunction(f, 90, monitor);
                println("\n=== " + name + " @ " + f.getEntryPoint() + " ===");
                if (results != null && results.decompileCompleted()
                    && results.getDecompiledFunction() != null) {
                    String body = results.getDecompiledFunction().getC();
                    println(body.substring(0, Math.min(body.length(), 25000)));
                } else println("NOT_DECOMPILED");
                count++;
                break;
            }
        }
        println("DECOMPILED_COUNT " + count);
        decomp.dispose();
    }
}
