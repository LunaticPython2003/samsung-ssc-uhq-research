import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;
import java.nio.file.Path;
import java.nio.file.Files;
import java.nio.charset.StandardCharsets;
public class DumpSscFull extends GhidraScript {
  public void run() throws Exception {
    String[] target={"a2dp_vendor_ssc_send_frames","a2dp_vendor_ssc_encoder_init","A2DP_VendorInitCodecConfigSsc"};
    String[] scriptArgs=getScriptArgs();
    if(scriptArgs.length != 1) throw new IllegalArgumentException("Pass output C path as first -postScript argument");
    String path=scriptArgs[0];
    DecompInterface d=new DecompInterface();d.openProgram(currentProgram);
    StringBuilder b=new StringBuilder();
    for(Function f:currentProgram.getFunctionManager().getFunctions(true)) {
      String name=f.getName();
      for(String key:target) {
        if(!name.contains(key)||f.isThunk())continue;
        DecompileResults r=d.decompileFunction(f,100,monitor);
        b.append("\n\n/* FUNCTION: ").append(name).append(" @ ").append(f.getEntryPoint()).append(" */\n");
        if(r!=null && r.decompileCompleted() && r.getDecompiledFunction()!=null)
           b.append(r.getDecompiledFunction().getC()).append("\n");
        else b.append("FAILED ").append(r==null?"null":r.getErrorMessage());
        println("EXTRACTED "+name+" bytes="+b.length());
        break;
      }
    }
    Files.writeString(Path.of(path),b.toString(),StandardCharsets.UTF_8);
    d.dispose();
    println("WRITTEN "+path+" bytes="+b.length());
  }
}
