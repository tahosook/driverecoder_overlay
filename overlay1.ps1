param(
  [string]$dirPath
)

$ffmpegPath = "..\ffmpeg-7.0.2-essentials_build\ffmpeg-7.0.2-essentials_build\bin\ffmpeg.exe"

Get-ChildItem -Path $dirPath -Filter *F.MP4 | ForEach-Object {
  $filename = $_.Name -replace "F.MP4$"
  $overlayFile = "${dirPath}/${filename}B.MP4"
  $outputFile = "${dirPath}/overlay/${filename}_overlay.MP4"
  if (Test-Path $overlayFile) {
     & $ffmpegPath -i $_.FullName -i $overlayFile -filter_complex "[0:v]crop=iw:ih*0.9,setpts=PTS/2[v0];[1:v]scale=iw/2.5:ih/2.5,crop=iw:ih*0.66,setpts=PTS/2[v1];[v0][v1]overlay=W-w-20:H-h-70[v]" -map "[v]" -c:v libx264 -preset veryfast -crf 23 -shortest $outputFile
#    & $ffmpegPath -i $_.FullName -i $overlayFile -filter_complex "[1:v]scale=iw/2.5:ih/2.5[v1];[0:v][v1]overlay=W-w-20:H-h-70,setpts=0.05*PTS[v];[0:a]anlmdn[a];[a]atempo=20[b]" -map "[v]" -map "[b]" -c:v libx264 -preset veryfast -crf 23 $outputFile
#    & $ffmpegPath -i $_.FullName -i $overlayFile -filter_complex "[1:v]scale=iw/2.5:ih/2.5[v1];[0:v][v1]overlay=W-w-20:H-h-70[v];[0:a]anlmdn[a]" -map "[v]" -map "[a]" -c:v libx264 -preset veryfast -crf 23 $outputFile
  } else {
    Write-Host "Error: Overlay file for $filename not found."
  }
}
