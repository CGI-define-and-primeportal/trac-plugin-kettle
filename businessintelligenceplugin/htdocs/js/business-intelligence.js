$(document).ready(function() {
  $("#content").find("h2").addAnchor(_("Link to this section"));

  var executions = 0;
  var executions_loading = false;
  function loadExecutions() {
    executions ++;
    executions_loading = true;
    var results_tables = $(".results-table");
    $(results_tables).each(function(i) {
      var table = $(this);
      var date = new Date().getTime();
      var result_url = table.attr("data-url") + "?nocache=" + date;
      // Load table's contents from URL
      $.ajax({
        url: result_url,
        success: function(data) {
          // Put results in DOM (hidden)
          var updated_contents = $("#ajax-results").html(data);
          // Check revision numbers against one another, update if different
          if($("td.rev", updated_contents).html() != $("td.rev", table).html()) {
            $("tbody", table).html(updated_contents.html());
            if(executions != 1) {
              $("tbody tr td", table).effect({
                duration: 2000,
                effect: "highlight",
                color: "#DFEEFD"
              });
            }
            $("tr td:first-child", table).remove();
          }
          if((i + 1) == results_tables.length) executions_loading = false;
        },
        error: function() {
          if((i + 1) == results_tables.length) executions_loading = false;
        }
      });
    });
  };

  loadExecutions();
  execution_interval = setInterval(function() { if(!executions_loading) loadExecutions(); }, 5000);

  $("#bi-integration-url-dialog").dialog({autoOpen:false,width:500, modal:true, title:"Report GET URL"});
  $("#content .get_url").click(function(){
    $("#bi-integration-url-placeholder").attr('href', this.href);
    $("#bi-integration-url-placeholder").html(this.href);
    $("#bi-integration-url-dialog").dialog('open');
    return false;
  });

  $("#dialogupload").dialog({autoOpen:false, width:500, modal:true, title:"Upload Transformations"});
  $("#uploadbutton").click(function(){
    $("#dialogupload").dialog('open');
    return false;
  });
  $(".execute-actions a[data-action]").click(function() {
    var execute_btn_handler = $(this).closest(".execute-actions");
    var group_label = $(".group-label", execute_btn_handler);
    if($(".btn.disabled", execute_btn_handler).length == 0) {
      $("#exec-action").val($(this).attr("data-action"));
      $("#exec-transform").val(execute_btn_handler.attr("data-transform"));
      group_label.html("<i class='icon-spin icon-spinner'></i>");
      $(".btn", execute_btn_handler).addClass("disabled");
      if($("#exec-action").val() != "execute_download") {
        $("#exec-form").ajaxSubmit({
          success: function() {
            $(".btn", execute_btn_handler).removeClass("disabled");
            group_label.html("<i class='icon-bolt'></i> Execute");
            loadExecutions();
          }
        });
      }
      else {
        setTimeout(function() {
          $(".btn", execute_btn_handler).removeClass("disabled");
          group_label.html("<i class='icon-bolt'></i> Execute");
        }, 30000);
        $("#exec-form").submit();
      }
    }
    execute_btn_handler.removeClass("open");
  });
});