<?xml version="1.0" encoding="utf-8"?>
<?python
import time
def ymd(stamp):
    return time.strftime('%Y-%m-%d', time.localtime(int(stamp)))
?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns:py="http://purl.org/kid/ns#">
  <head>
    <title py:content="'RepoView: %s' % repo_data['title']"/>
    <style type="text/css" media="screen">
      @import url("layout/fedora.css");
      @import url("layout/pkgdb.css");
      @import url("layout/style.css");
    </style>
    <meta name="robots" content="noindex,follow" />
  </head>

  <body>
    <div id="wrapper">
      <div id="head">
        <h1><a href="http://fedoraproject.org/index.html">Fedora</a></h1>
      </div>

       <div id="content">
          <p class="nav">Jump to letter: [
          <span class="letterlist">
            <a py:for="letter in repo_data['letters']"
              class="nlink"
              href="${'letter_%s.group.html' % letter.lower()}" py:content="letter"/>
          </span>]
        </p>   
        <h2 py:content="group_data['name']"/>
	<p py:content="group_data['description']"/>
        <ul>
          <li py:for="(name, filename, summary) in group_data['packages']">
            <a href="${filename}" class="inpage" py:content="name"/> - 
            <span py:content="summary"/>
          </li>
        </ul>

   </div>
   </div>    
    <div id="bottom">
      <div id="footer">
        <p>
          <span py:content="'Listing generated: %s by' % ymd(time.time())"/>
          <a href="http://mricon.com/trac/wiki/Repoview"
            class="repoview" py:content="'RepoView-%s' % repo_data['my_version']"/>
        </p>
       
      </div>
    </div>
  </body>
</html>




