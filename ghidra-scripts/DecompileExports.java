import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;

public class DecompileExports extends GhidraScript {
    public void run() throws Exception {
        String[] wanted = {
            "ssc_encoder_create", "ssc_encoder_get_size", "ssc_encoder_init",
            "ssc_encode", "ssc_encoder_destroy", "get_uhq_info_from_bitrate",
            "ssc_custom_mode_create"
        };
        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);
        for (Function f : it) {
            for (String name : wanted) {
                if (f.getName().equals(name)) {
                    println("\n===== " + f.getName() + " @ " + f.getEntryPoint() + " =====");
                    println("Signature: " + f.getSignature());
                    DecompileResults result = decomp.decompileFunction(f, 90, monitor);
                    if (result != null && result.decompileCompleted() && result.getDecompiledFunction() != null) {
                        println(result.getDecompiledFunction().getC());
                    } else {
                        println("DECOMPILER: " + (result == null ? "no result" : result.getErrorMessage()));
                    }
                }
            }
        }
        decomp.dispose();
    }
}
