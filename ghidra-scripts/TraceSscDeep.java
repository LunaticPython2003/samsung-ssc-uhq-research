import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
public class TraceSscDeep extends GhidraScript {
  public void run() throws Exception {
    String[] names={
      "A2DP_VendorUsesRtpHeaderSsc",
      "A2DP_VendorGetTrackBitrateLimitationSsc",
      "A2DP_VendorGetSscType",
      "A2DP_VendorAdjustCodecSsc",
      "a2dp_vendor_ssc_get_encoder_interval_ms",
      "a2dp_vendor_ssc_get_effective_frame_size",
      "a2dp_vendor_ssc_get_queue_time_ms",
      "A2DP_IsVendorSourceCodecValidSsc",
      "A2DP_IsVendorPeerSinkCodecValidSsc"
    };
    DecompInterface d=new DecompInterface();d.openProgram(currentProgram);
    for(Function f:currentProgram.getFunctionManager().getFunctions(true)) {
      if(f.isThunk())continue;
      for(String key:names) {
        if(f.getName().contains(key) && !f.getName().contains("Globals")) {
          DecompileResults r=d.decompileFunction(f,50,monitor);
          println("### TARGET "+f.getName()+" @ "+f.getEntryPoint());
          if(r!=null && r.decompileCompleted() && r.getDecompiledFunction()!=null) {
            String code=r.getDecompiledFunction().getC();
            println(code.substring(0,Math.min(code.length(),16000)));
          } else println("DECOMP_ERR "+(r==null?"null":r.getErrorMessage()));
          break;
        }
      }
    }
    d.dispose();
  }
}
